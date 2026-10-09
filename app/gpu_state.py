"""Shared DynamoDB state: conditional transitions protect startup, shutdown and inference."""

import time
import uuid

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.exceptions import ClientError


class TransitionConflict(Exception):
    pass


class GpuState:
    def __init__(self, client, table):
        self.client, self.table = client, table
        self.serializer, self.deserializer = TypeSerializer(), TypeDeserializer()

    def encode(self, values):
        return {key: self.serializer.serialize(value) for key, value in values.items()}

    def get(self):
        response = self.client.get_item(
            TableName=self.table, Key=self.encode({"pk": "GPU"}), ConsistentRead=True
        )
        if "Item" not in response:
            initial = {
                "pk": "GPU",
                "desired": "stopped",
                "phase": "stopped",
                "requested_at": 0,
                "last_activity": 0,
                "busy_until": 0,
                "instance_count": 0,
            }
            try:
                self.client.put_item(
                    TableName=self.table,
                    Item=self.encode(initial),
                    ConditionExpression="attribute_not_exists(pk)",
                )
            except ClientError as error:
                if error.response["Error"]["Code"] != "ConditionalCheckFailedException":
                    raise
                return self.get()
            return initial
        return {
            key: self.deserializer.deserialize(value) for key, value in response["Item"].items()
        }

    def update(self, expression, values, *, condition=None):
        options = {"ConditionExpression": condition} if condition else {}
        try:
            response = self.client.update_item(
                TableName=self.table,
                Key=self.encode({"pk": "GPU"}),
                UpdateExpression=expression,
                ExpressionAttributeValues=self.encode(values),
                ReturnValues="ALL_NEW",
                **options,
            )
        except ClientError as error:
            if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise TransitionConflict from error
            raise
        return {
            key: self.deserializer.deserialize(value)
            for key, value in response["Attributes"].items()
        }

    def start(self, now=None):
        now = int(time.time()) if now is None else now
        current = self.get()
        if current["desired"] == "running":
            return current
        return self.update(
            "SET desired=:run, phase=:starting, requested_at=:now, starting_at=:now, "
            "last_activity=:now, stop_reason=:empty REMOVE endpoint",
            {
                ":run": "running",
                ":starting": "starting",
                ":now": now,
                ":empty": "",
                ":off": "stopped",
                ":error": "error",
            },
            condition="desired=:off AND (phase=:off OR phase=:error)",
        )

    def stop(self, now=None):
        now = int(time.time()) if now is None else now
        current = self.get()
        if current["desired"] == "stopped":
            return current
        return self.update(
            "SET desired=:off, phase=:stopping, requested_at=:now, stop_reason=:reason REMOVE endpoint",
            {
                ":off": "stopped",
                ":stopping": "stopping",
                ":now": now,
                ":reason": "manual",
                ":run": "running",
            },
            condition="desired=:run",
        )

    def acquire(self, seconds, now=None):
        now = int(time.time()) if now is None else now
        token = uuid.uuid4().hex
        state = self.update(
            "SET busy_until=:until, lease_token=:token, last_activity=:now",
            {
                ":until": now + seconds,
                ":token": token,
                ":now": now,
                ":run": "running",
                ":ready": "ready",
            },
            condition="desired=:run AND phase=:ready AND attribute_exists(endpoint) AND busy_until<=:now",
        )
        return token, state["endpoint"]

    def release(self, token, *, cooldown=0, now=None):
        now = int(time.time()) if now is None else now
        try:
            self.update(
                "SET busy_until=:until, last_activity=:now REMOVE lease_token",
                {":until": now + cooldown, ":now": now, ":token": token},
                condition="lease_token=:token",
            )
        except TransitionConflict:
            pass
