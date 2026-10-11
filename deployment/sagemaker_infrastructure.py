"""Private SageMaker invocation and an on-demand endpoint lifecycle."""

from pathlib import Path

from deployment.infrastructure import attr, ref, sub


def template():
    resources = {}

    def add(name, kind, properties, **options):
        resources[name] = {"Type": "AWS::" + kind, "Properties": properties, **options}

    endpoint_arn = sub(
        "arn:${AWS::Partition}:sagemaker:${AWS::Region}:${AWS::AccountId}:endpoint/${EndpointName}"
    )
    state_arn = sub(
        "arn:${AWS::Partition}:dynamodb:${AWS::Region}:${AWS::AccountId}:table/${StateTableName}"
    )
    add(
        "EndpointLog",
        "Logs::LogGroup",
        {
            "LogGroupName": sub("/aws/sagemaker/Endpoints/${EndpointName}"),
            "RetentionInDays": 14,
        },
    )
    add(
        "ModelRole",
        "IAM::Role",
        {
            "AssumeRolePolicyDocument": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"Service": "sagemaker.amazonaws.com"},
                        "Action": "sts:AssumeRole",
                        "Condition": {"StringEquals": {"aws:SourceAccount": ref("AWS::AccountId")}},
                    }
                ],
            },
            "Policies": [
                {
                    "PolicyName": "ModelImagesAndLogs",
                    "PolicyDocument": {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Action": "ecr:GetAuthorizationToken",
                                "Resource": "*",
                            },
                            {
                                "Effect": "Allow",
                                "Action": [
                                    "ecr:BatchCheckLayerAvailability",
                                    "ecr:GetDownloadUrlForLayer",
                                    "ecr:BatchGetImage",
                                ],
                                "Resource": ref("ModelRepositoryArn"),
                            },
                            {
                                "Effect": "Allow",
                                "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
                                "Resource": attr("EndpointLog", "Arn"),
                            },
                        ],
                    },
                }
            ],
        },
    )
    add(
        "Model",
        "SageMaker::Model",
        {
            "ModelName": sub("${EndpointName}-${ModelRevision}"),
            "ExecutionRoleArn": attr("ModelRole", "Arn"),
            "EnableNetworkIsolation": True,
            "PrimaryContainer": {"Image": ref("ModelImage")},
        },
    )
    add(
        "EndpointConfig",
        "SageMaker::EndpointConfig",
        {
            "EndpointConfigName": sub("${EndpointName}-${ModelRevision}-gpu4"),
            "ProductionVariants": [
                {
                    "VariantName": "AllTraffic",
                    "ModelName": attr("Model", "ModelName"),
                    "InstanceType": "ml.g6.xlarge",
                    "InferenceAmiVersion": "al2023-ami-sagemaker-inference-gpu-4-1",
                    "InitialInstanceCount": 1,
                    "InitialVariantWeight": 1,
                    "ContainerStartupHealthCheckTimeoutInSeconds": 900,
                    "ModelDataDownloadTimeoutInSeconds": 900,
                }
            ],
        },
    )
    add(
        "RuntimeEndpoint",
        "EC2::VPCEndpoint",
        {
            "VpcId": ref("VpcId"),
            "VpcEndpointType": "Interface",
            "ServiceName": sub("com.amazonaws.${AWS::Region}.sagemaker.runtime"),
            "PrivateDnsEnabled": True,
            "SubnetIds": [ref("SubnetId")],
            "SecurityGroupIds": [ref("EndpointSecurityGroup")],
            "PolicyDocument": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": "*",
                        "Action": "sagemaker:InvokeEndpoint",
                        "Resource": endpoint_arn,
                    }
                ],
            },
        },
    )
    add(
        "ControllerLog",
        "Logs::LogGroup",
        {"LogGroupName": sub("/aws/lambda/${AWS::StackName}-controller"), "RetentionInDays": 7},
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
                    "PolicyName": "ManageOneEndpoint",
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
                                "Resource": state_arn,
                            },
                            {
                                "Effect": "Allow",
                                "Action": "sagemaker:CreateEndpoint",
                                "Resource": [
                                    endpoint_arn,
                                    attr("EndpointConfig", "EndpointConfigArn"),
                                ],
                            },
                            {
                                "Effect": "Allow",
                                "Action": [
                                    "sagemaker:DescribeEndpoint",
                                    "sagemaker:DeleteEndpoint",
                                    "sagemaker:AddTags",
                                ],
                                "Resource": endpoint_arn,
                            },
                            {
                                "Effect": "Allow",
                                "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
                                "Resource": attr("ControllerLog", "Arn"),
                            },
                        ],
                    },
                }
            ],
        },
    )
    root = Path(__file__).resolve().parent.parent
    code = (
        (root / "app/gpu_state.py").read_text()
        + "\n\n"
        + (root / "deployment/sagemaker_controller.py")
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
            "Code": {"ZipFile": code},
            "Environment": {
                "Variables": {
                    "GPU_STATE_TABLE": ref("StateTableName"),
                    "ENDPOINT_NAME": ref("EndpointName"),
                    "ENDPOINT_CONFIG": attr("EndpointConfig", "EndpointConfigName"),
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
            "State": ref("ControllerState"),
            "Targets": [{"Id": "Controller", "Arn": attr("Controller", "Arn")}],
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
        "Description": "Decider SageMaker GPU, private runtime endpoint and idle deletion.",
        "Parameters": {
            "ControllerState": {
                "Type": "String",
                "Default": "ENABLED",
                "AllowedValues": ["ENABLED", "DISABLED"],
            },
            **{
                k: {"Type": "String"}
                for k in [
                    "VpcId",
                    "SubnetId",
                    "EndpointSecurityGroup",
                    "ModelRepositoryArn",
                    "ModelImage",
                    "StateTableName",
                    "EndpointName",
                    "ModelRevision",
                ]
            },
        },
        "Resources": resources,
        "Outputs": {
            k: {"Value": v}
            for k, v in {
                "EndpointName": ref("EndpointName"),
                "EndpointConfigName": attr("EndpointConfig", "EndpointConfigName"),
                "ModelName": attr("Model", "ModelName"),
                "ControllerName": ref("Controller"),
                "StateTableName": ref("StateTableName"),
            }.items()
        },
    }
