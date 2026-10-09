"""Spot-only GPU capacity, private ECS connectivity and a scheduled scale-to-zero controller."""

import json
from pathlib import Path

if __package__:
    from .infrastructure import attr, ref, sub
else:
    from infrastructure import attr, ref, sub


def template():
    resources = {}

    def add(name, kind, properties, **options):
        resources[name] = {"Type": "AWS::" + kind, "Properties": properties, **options}

    add(
        "StateTable",
        "DynamoDB::Table",
        {
            "BillingMode": "PAY_PER_REQUEST",
            "AttributeDefinitions": [{"AttributeName": "pk", "AttributeType": "S"}],
            "KeySchema": [{"AttributeName": "pk", "KeyType": "HASH"}],
            "SSESpecification": {"SSEEnabled": True},
        },
    )
    add(
        "GpuSecurityGroup",
        "EC2::SecurityGroup",
        {
            "VpcId": ref("VpcId"),
            "GroupDescription": "Private model port from the API only",
            "SecurityGroupIngress": [
                {
                    "IpProtocol": "tcp",
                    "FromPort": 8099,
                    "ToPort": 8099,
                    "SourceSecurityGroupId": ref("ApiSecurityGroup"),
                }
            ],
        },
    )
    add(
        "GpuSubnet3",
        "EC2::Subnet",
        {
            "VpcId": ref("VpcId"),
            "AvailabilityZone": sub("${AWS::Region}c"),
            "CidrBlock": "10.78.3.0/24",
            "MapPublicIpOnLaunch": False,
        },
    )
    add(
        "GpuSubnet3Route",
        "EC2::SubnetRouteTableAssociation",
        {
            "SubnetId": ref("GpuSubnet3"),
            "RouteTableId": ref("PrivateRouteTableId"),
        },
    )
    add(
        "GpuEndpointAccess",
        "EC2::SecurityGroupIngress",
        {
            "GroupId": ref("EndpointSecurityGroup"),
            "IpProtocol": "tcp",
            "FromPort": 443,
            "ToPort": 443,
            "SourceSecurityGroupId": ref("GpuSecurityGroup"),
        },
    )
    for name, service in [
        ("EcsEndpoint", "ecs"),
        ("AgentEndpoint", "ecs-agent"),
        ("TelemetryEndpoint", "ecs-telemetry"),
    ]:
        add(
            name,
            "EC2::VPCEndpoint",
            {
                "VpcId": ref("VpcId"),
                "VpcEndpointType": "Interface",
                "PrivateDnsEnabled": True,
                "ServiceName": sub(f"com.amazonaws.${{AWS::Region}}.{service}"),
                # One endpoint ENI per service keeps idle cost lower; all GPU subnets can reach it.
                "SubnetIds": [{"Fn::Select": [0, ref("SubnetIds")]}],
                "SecurityGroupIds": [ref("EndpointSecurityGroup")],
            },
        )
    add(
        "InstanceRole",
        "IAM::Role",
        {
            "AssumeRolePolicyDocument": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"Service": "ec2.amazonaws.com"},
                        "Action": "sts:AssumeRole",
                    }
                ],
            },
            "ManagedPolicyArns": [
                sub(
                    "arn:${AWS::Partition}:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role"
                )
            ],
        },
    )
    add("InstanceProfile", "IAM::InstanceProfile", {"Roles": [ref("InstanceRole")]})
    add(
        "LaunchTemplate",
        "EC2::LaunchTemplate",
        {
            "LaunchTemplateData": {
                "ImageId": ref("GpuAmiId"),
                "InstanceType": "g6.xlarge",
                "IamInstanceProfile": {"Arn": attr("InstanceProfile", "Arn")},
                "SecurityGroupIds": [ref("GpuSecurityGroup")],
                "MetadataOptions": {"HttpTokens": "required", "HttpPutResponseHopLimit": 1},
                "BlockDeviceMappings": [
                    {
                        "DeviceName": "/dev/xvda",
                        "Ebs": {
                            "VolumeType": "gp3",
                            "VolumeSize": 80,
                            "Encrypted": True,
                            "DeleteOnTermination": True,
                        },
                    }
                ],
                "TagSpecifications": [
                    {
                        "ResourceType": "instance",
                        "Tags": [
                            {"Key": "Name", "Value": sub("${AWS::StackName}-spot")},
                            {"Key": "Project", "Value": "StrandsDecider"},
                        ],
                    }
                ],
                "UserData": {
                    "Fn::Base64": sub(
                        "#!/bin/bash\nset -eu\n"
                        "cat >> /etc/ecs/ecs.config <<'EOF'\n"
                        "ECS_CLUSTER=${ClusterName}\nECS_ENABLE_GPU_SUPPORT=true\n"
                        "ECS_ENABLE_SPOT_INSTANCE_DRAINING=true\nECS_RESERVED_MEMORY=512\n"
                        "ECS_IMAGE_PULL_BEHAVIOR=prefer-cached\nEOF\n"
                    )
                },
            },
        },
    )
    add(
        "GpuAsg",
        "AutoScaling::AutoScalingGroup",
        {
            "MinSize": "0",
            "MaxSize": "1",
            "DesiredCapacity": "0",
            "VPCZoneIdentifier": [
                {"Fn::Select": [0, ref("SubnetIds")]},
                {"Fn::Select": [1, ref("SubnetIds")]},
                ref("GpuSubnet3"),
            ],
            "HealthCheckGracePeriod": 600,
            "MixedInstancesPolicy": {
                "LaunchTemplate": {
                    "LaunchTemplateSpecification": {
                        "LaunchTemplateId": ref("LaunchTemplate"),
                        "Version": attr("LaunchTemplate", "LatestVersionNumber"),
                    },
                    "Overrides": [
                        {"InstanceType": name}
                        for name in (
                            "g6.xlarge",
                            "g6.2xlarge",
                            "g5.xlarge",
                        )
                    ],
                },
                "InstancesDistribution": {
                    "OnDemandBaseCapacity": 0,
                    "OnDemandPercentageAboveBaseCapacity": 0,
                    "SpotAllocationStrategy": "price-capacity-optimized",
                    "SpotMaxPrice": "0.55",
                },
            },
            "Tags": [{"Key": "AmazonECSManaged", "Value": "true", "PropagateAtLaunch": True}],
        },
        DependsOn=["EcsEndpoint", "AgentEndpoint", "TelemetryEndpoint"],
    )
    add(
        "CapacityProvider",
        "ECS::CapacityProvider",
        {
            "AutoScalingGroupProvider": {
                "AutoScalingGroupArn": ref("GpuAsg"),
                "ManagedScaling": {"Status": "DISABLED"},
                "ManagedTerminationProtection": "DISABLED",
                "ManagedDraining": "ENABLED",
            },
        },
    )
    add(
        "ClusterProviders",
        "ECS::ClusterCapacityProviderAssociations",
        {
            "Cluster": ref("ClusterName"),
            "CapacityProviders": ["FARGATE", "FARGATE_SPOT", ref("CapacityProvider")],
            "DefaultCapacityProviderStrategy": [{"CapacityProvider": "FARGATE", "Weight": 1}],
        },
    )
    add(
        "GpuTask",
        "ECS::TaskDefinition",
        {
            "Family": sub("${AWS::StackName}-model"),
            "RequiresCompatibilities": ["EC2"],
            "NetworkMode": "host",
            "ExecutionRoleArn": ref("ExecutionRoleArn"),
            "RuntimePlatform": {"CpuArchitecture": "X86_64", "OperatingSystemFamily": "LINUX"},
            "ContainerDefinitions": [
                {
                    "Name": "model",
                    "Image": sub("${ModelRepositoryUri}:${GpuImageTag}"),
                    "Essential": True,
                    "Cpu": 3072,
                    "Memory": 12288,
                    "User": "10001",
                    "StopTimeout": 120,
                    "ResourceRequirements": [{"Type": "GPU", "Value": "1"}],
                    "PortMappings": [{"ContainerPort": 8099, "HostPort": 8099, "Protocol": "tcp"}],
                    "LogConfiguration": {
                        "LogDriver": "awslogs",
                        "Options": {
                            "awslogs-group": ref("LogGroupName"),
                            "awslogs-region": ref("AWS::Region"),
                            "awslogs-stream-prefix": "gpu",
                            "mode": "non-blocking",
                            "max-buffer-size": "5m",
                        },
                    },
                    "HealthCheck": {
                        "Command": [
                            "CMD-SHELL",
                            "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8099/health', timeout=3)\"",
                        ],
                        "Interval": 15,
                        "Timeout": 5,
                        "Retries": 3,
                        "StartPeriod": 300,
                    },
                }
            ],
        },
    )
    add(
        "GpuService",
        "ECS::Service",
        {
            "Cluster": ref("ClusterName"),
            "ServiceName": sub("${AWS::StackName}-model"),
            "TaskDefinition": ref("GpuTask"),
            "DesiredCount": 0,
            "CapacityProviderStrategy": [
                {"CapacityProvider": ref("CapacityProvider"), "Weight": 1}
            ],
            "DeploymentConfiguration": {"MinimumHealthyPercent": 0, "MaximumPercent": 100},
        },
        DependsOn=["ClusterProviders"],
    )
    add(
        "ControllerRole",
        "IAM::Role",
        {
            "AssumeRolePolicyDocument": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"Service": "lambda.amazonaws.com"},
                        "Action": "sts:AssumeRole",
                    }
                ],
            },
            "Policies": [
                {
                    "PolicyName": "GpuLifecycle",
                    "PolicyDocument": {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Action": [
                                    "dynamodb:GetItem",
                                    "dynamodb:PutItem",
                                    "dynamodb:UpdateItem",
                                ],
                                "Resource": attr("StateTable", "Arn"),
                            },
                            {
                                "Effect": "Allow",
                                "Action": ["ecs:DescribeServices", "ecs:UpdateService"],
                                "Resource": ref("GpuService"),
                            },
                            {
                                "Effect": "Allow",
                                "Action": [
                                    "ecs:ListTasks",
                                    "ecs:DescribeTasks",
                                    "ecs:DescribeContainerInstances",
                                ],
                                "Resource": "*",
                                "Condition": {
                                    "ArnEquals": {
                                        "ecs:cluster": sub(
                                            "arn:${AWS::Partition}:ecs:${AWS::Region}:${AWS::AccountId}:cluster/${ClusterName}"
                                        )
                                    }
                                },
                            },
                            {
                                "Effect": "Allow",
                                "Action": "autoscaling:SetDesiredCapacity",
                                "Resource": sub(
                                    "arn:${AWS::Partition}:autoscaling:${AWS::Region}:${AWS::AccountId}:autoScalingGroup:*:autoScalingGroupName/${GpuAsg}"
                                ),
                            },
                            {
                                "Effect": "Allow",
                                "Action": [
                                    "autoscaling:DescribeAutoScalingGroups",
                                    "ec2:DescribeInstances",
                                ],
                                "Resource": "*",
                            },
                            {
                                "Effect": "Allow",
                                "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
                                "Resource": sub("${ControllerLog.Arn}:*"),
                            },
                        ],
                    },
                }
            ],
        },
    )
    add(
        "ControllerLog",
        "Logs::LogGroup",
        {
            "LogGroupName": sub("/aws/lambda/${AWS::StackName}-controller"),
            "RetentionInDays": 7,
        },
    )
    root = Path(__file__).resolve().parent.parent
    state_code = (root / "app/gpu_state.py").read_text()
    controller_code = (
        (root / "deployment/gpu_controller.py")
        .read_text()
        .replace("from app.gpu_state import GpuState, TransitionConflict", "")
    )
    add(
        "Controller",
        "Lambda::Function",
        {
            "FunctionName": sub("${AWS::StackName}-controller"),
            "Runtime": "python3.12",
            "Handler": "index.handler",
            "Timeout": 45,
            "MemorySize": 256,
            "ReservedConcurrentExecutions": 1,
            "Role": attr("ControllerRole", "Arn"),
            "Code": {"ZipFile": state_code + "\n\n" + controller_code},
            "Environment": {
                "Variables": {
                    "GPU_STATE_TABLE": ref("StateTable"),
                    "GPU_CLUSTER": ref("ClusterName"),
                    "GPU_SERVICE": attr("GpuService", "Name"),
                    "GPU_ASG": ref("GpuAsg"),
                }
            },
        },
        DependsOn=["ControllerLog"],
    )
    add(
        "Schedule",
        "Events::Rule",
        {
            "ScheduleExpression": "rate(1 minute)",
            "State": "ENABLED",
            "Targets": [{"Id": "GpuController", "Arn": attr("Controller", "Arn")}],
        },
    )
    add(
        "SchedulePermission",
        "Lambda::Permission",
        {
            "Action": "lambda:InvokeFunction",
            "FunctionName": ref("Controller"),
            "Principal": "events.amazonaws.com",
            "SourceArn": attr("Schedule", "Arn"),
        },
    )
    return {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Description": "Strands Decider: private g6/g5 Spot GPU, capped hourly price and zero idle capacity.",
        "Parameters": {
            **{
                key: {"Type": "String"}
                for key in [
                    "VpcId",
                    "PrivateRouteTableId",
                    "ApiSecurityGroup",
                    "EndpointSecurityGroup",
                    "ClusterName",
                    "ExecutionRoleArn",
                    "LogGroupName",
                    "ModelRepositoryUri",
                    "GpuImageTag",
                ]
            },
            "SubnetIds": {"Type": "List<AWS::EC2::Subnet::Id>"},
            "GpuAmiId": {
                "Type": "AWS::SSM::Parameter::Value<AWS::EC2::Image::Id>",
                "Default": "/aws/service/ecs/optimized-ami/amazon-linux-2023/gpu/recommended/image_id",
            },
        },
        "Resources": resources,
        "Outputs": {
            key: {"Value": value}
            for key, value in {
                "StateTableName": ref("StateTable"),
                "StateTableArn": attr("StateTable", "Arn"),
                "AsgName": ref("GpuAsg"),
                "ServiceName": attr("GpuService", "Name"),
                "ControllerName": ref("Controller"),
                "GpuSecurityGroupId": ref("GpuSecurityGroup"),
            }.items()
        },
    }


if __name__ == "__main__":
    print(json.dumps(template(), indent=2))
