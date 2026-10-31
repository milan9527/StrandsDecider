import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError

import optimized_all_models_infra as infra


class InvocationVisibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ac-ssm-test-")
        self.root = Path(self.temp.name)
        self.path = self.root / "operations/start-model.json"
        self.path.parent.mkdir()
        self.operation = {
            "id": "existing-command", "instance": "test-instance", "region": "us-east-1",
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        }
        self.path.write_text(json.dumps(self.operation))
        self.client = Mock()
        self.client.get_command_invocation.side_effect = ClientError(
            {"Error": {"Code": "InvocationDoesNotExist"}}, "GetCommandInvocation")

    def tearDown(self):
        self.temp.cleanup()

    def poll(self):
        with patch.object(infra, "ROOT", self.root), patch.object(infra.boto3, "client", return_value=self.client):
            return infra.status("start-model")

    def test_recently_submitted_command_is_pending_then_visible(self):
        self.assertEqual(self.poll()["Status"], "Pending")
        self.client.get_command_invocation.side_effect = None
        self.client.get_command_invocation.return_value = {"Status": "Success", "ResponseCode": 0}
        self.assertEqual(self.poll()["Status"], "Success")
        self.assertEqual(self.client.get_command_invocation.call_count, 2)
        self.client.get_command_invocation.assert_called_with(
            CommandId="existing-command", InstanceId="test-instance")
        self.client.send_command.assert_not_called()
        self.assertEqual(json.loads(self.path.read_text()), self.operation)

    def test_missing_old_command_remains_an_error(self):
        self.operation["submitted_at"] = (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat()
        self.path.write_text(json.dumps(self.operation))
        with self.assertRaises(ClientError):
            self.poll()

    def test_unrelated_errors_are_not_hidden(self):
        self.client.get_command_invocation.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException"}}, "GetCommandInvocation")
        with self.assertRaises(ClientError):
            self.poll()


if __name__ == "__main__":
    unittest.main()
