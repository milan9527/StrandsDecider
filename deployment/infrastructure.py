"""Generate the CloudFormation template: private S3/OAC and private ECS/VPC origin."""

import json
from pathlib import Path


def ref(name):
    return {"Ref": name}


def attr(name, field):
    return {"Fn::GetAtt": [name, field]}


def sub(value):
    return {"Fn::Sub": value}


def template():
    resources = {}

    def add(name, kind, properties, **options):
        resources[name] = {"Type": f"AWS::{kind}", "Properties": properties, **options}

    add(
        "Vpc",
        "EC2::VPC",
        {
            "CidrBlock": "10.78.0.0/16",
            "EnableDnsSupport": True,
            "EnableDnsHostnames": True,
            "Tags": [{"Key": "Name", "Value": sub("${AWS::StackName}")}],
        },
    )
    add("InternetGateway", "EC2::InternetGateway", {})
    add(
        "GatewayAttachment",
        "EC2::VPCGatewayAttachment",
        {
            "VpcId": ref("Vpc"),
            "InternetGatewayId": ref("InternetGateway"),
        },
    )
    add("PrivateRoutes", "EC2::RouteTable", {"VpcId": ref("Vpc")})
    for n, cidr in [(1, "10.78.1.0/24"), (2, "10.78.2.0/24")]:
        add(
            f"Subnet{n}",
            "EC2::Subnet",
            {
                "VpcId": ref("Vpc"),
                "AvailabilityZone": ref(f"AvailabilityZone{n}"),
                "CidrBlock": cidr,
                "MapPublicIpOnLaunch": False,
            },
        )
        add(
            f"SubnetRoute{n}",
            "EC2::SubnetRouteTableAssociation",
            {
                "SubnetId": ref(f"Subnet{n}"),
                "RouteTableId": ref("PrivateRoutes"),
            },
        )
    subnets = [ref("Subnet1"), ref("Subnet2")]
    add(
        "TaskSecurityGroup",
        "EC2::SecurityGroup",
        {
            "VpcId": ref("Vpc"),
            "GroupDescription": "Decider API and model task; no public ingress",
        },
    )
    add(
        "EndpointSecurityGroup",
        "EC2::SecurityGroup",
        {
            "VpcId": ref("Vpc"),
            "GroupDescription": "Private AWS endpoints for ECS image pulls and logs",
            "SecurityGroupIngress": [
                {
                    "IpProtocol": "tcp",
                    "FromPort": 443,
                    "ToPort": 443,
                    "SourceSecurityGroupId": ref("TaskSecurityGroup"),
                }
            ],
        },
    )
    add(
        "AlbSecurityGroup",
        "EC2::SecurityGroup",
        {
            "VpcId": ref("Vpc"),
            "GroupDescription": "CloudFront VPC origin to internal ALB only",
            "SecurityGroupIngress": [
                {
                    "IpProtocol": "tcp",
                    "FromPort": 80,
                    "ToPort": 80,
                    "SourcePrefixListId": ref("CloudFrontPrefixListId"),
                }
            ],
            "SecurityGroupEgress": [
                {
                    "IpProtocol": "tcp",
                    "FromPort": 8000,
                    "ToPort": 8000,
                    "DestinationSecurityGroupId": ref("TaskSecurityGroup"),
                }
            ],
        },
    )
    add(
        "TaskIngress",
        "EC2::SecurityGroupIngress",
        {
            "GroupId": ref("TaskSecurityGroup"),
            "IpProtocol": "tcp",
            "FromPort": 8000,
            "ToPort": 8000,
            "SourceSecurityGroupId": ref("AlbSecurityGroup"),
        },
    )
    for name, service in [
        ("EcrApiEndpoint", "ecr.api"),
        ("EcrDockerEndpoint", "ecr.dkr"),
        ("LogsEndpoint", "logs"),
    ]:
        add(
            name,
            "EC2::VPCEndpoint",
            {
                "VpcId": ref("Vpc"),
                "VpcEndpointType": "Interface",
                "PrivateDnsEnabled": True,
                "ServiceName": sub(f"com.amazonaws.${{AWS::Region}}.{service}"),
                "SubnetIds": subnets,
                "SecurityGroupIds": [ref("EndpointSecurityGroup")],
            },
        )
    bedrock_resources = [
        sub(
            "arn:${AWS::Partition}:bedrock:${AWS::Region}:${AWS::AccountId}:inference-profile/us.openai.gpt-6.1-sol"
        ),
        *[
            sub(f"arn:${{AWS::Partition}}:bedrock:{region}::foundation-model/openai.gpt-6.1-sol")
            for region in ("us-east-1", "us-east-2", "us-west-2")
        ],
    ]
    # The routing module validates targets against the regional catalog before invocation.
    # Profiles can route to the US destinations advertised by that catalog.
    routing_resources = [
        sub(
            "arn:${AWS::Partition}:bedrock:${AWS::Region}:${AWS::AccountId}:inference-profile/us.openai.gpt-6-sol"
        ),
        *[
            sub(f"arn:${{AWS::Partition}}:bedrock:{region}::foundation-model/openai.gpt-6-sol")
            for region in ("us-east-1", "us-east-2", "us-west-2")
        ],
        sub("arn:${AWS::Partition}:bedrock:${AWS::Region}:${AWS::AccountId}:inference-profile/*"),
        *[
            sub(f"arn:${{AWS::Partition}}:bedrock:{region}::foundation-model/*")
            for region in ("us-east-1", "us-east-2", "us-west-1", "us-west-2", "")
        ],
    ]
    add(
        "BedrockRuntimeEndpoint",
        "EC2::VPCEndpoint",
        {
            "VpcId": ref("Vpc"),
            "VpcEndpointType": "Interface",
            "PrivateDnsEnabled": True,
            "ServiceName": sub("com.amazonaws.${AWS::Region}.bedrock-runtime"),
            "SubnetIds": [ref("Subnet1")],
            "SecurityGroupIds": [ref("EndpointSecurityGroup")],
            "PolicyDocument": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": "*",
                        "Action": "bedrock:InvokeModel",
                        "Resource": bedrock_resources,
                    },
                    {
                        "Effect": "Allow",
                        "Principal": "*",
                        "Action": "bedrock:InvokeModel",
                        "Resource": routing_resources,
                    },
                ],
            },
        },
    )
    add(
        "S3Endpoint",
        "EC2::VPCEndpoint",
        {
            "VpcId": ref("Vpc"),
            "VpcEndpointType": "Gateway",
            "ServiceName": sub("com.amazonaws.${AWS::Region}.s3"),
            "RouteTableIds": [ref("PrivateRoutes")],
        },
    )
    for name, suffix in [("ApiRepository", "api"), ("ModelRepository", "model")]:
        add(
            name,
            "ECR::Repository",
            {
                "RepositoryName": sub(f"${{AWS::StackName}}-{suffix}"),
                "ImageTagMutability": "IMMUTABLE",
                "ImageScanningConfiguration": {"ScanOnPush": True},
                "EncryptionConfiguration": {"EncryptionType": "AES256"},
                "LifecyclePolicy": {
                    "LifecyclePolicyText": json.dumps(
                        {
                            "rules": [
                                {
                                    "rulePriority": 1,
                                    "description": "Expire untagged build layers after seven days",
                                    "selection": {
                                        "tagStatus": "untagged",
                                        "countType": "sinceImagePushed",
                                        "countUnit": "days",
                                        "countNumber": 7,
                                    },
                                    "action": {"type": "expire"},
                                }
                            ]
                        }
                    )
                },
            },
            DeletionPolicy="Retain",
            UpdateReplacePolicy="Retain",
        )
    add(
        "AuthTable",
        "DynamoDB::Table",
        {
            "TableName": sub("${AWS::StackName}-auth"),
            "BillingMode": "PAY_PER_REQUEST",
            "AttributeDefinitions": [{"AttributeName": "pk", "AttributeType": "S"}],
            "KeySchema": [{"AttributeName": "pk", "KeyType": "HASH"}],
            "TimeToLiveSpecification": {"AttributeName": "expires_at", "Enabled": True},
            "SSESpecification": {"SSEEnabled": True},
            "PointInTimeRecoverySpecification": {"PointInTimeRecoveryEnabled": True},
        },
        DeletionPolicy="Retain",
        UpdateReplacePolicy="Retain",
    )
    add(
        "DynamoEndpoint",
        "EC2::VPCEndpoint",
        {
            "VpcId": ref("Vpc"),
            "VpcEndpointType": "Gateway",
            "ServiceName": sub("com.amazonaws.${AWS::Region}.dynamodb"),
            "RouteTableIds": [ref("PrivateRoutes")],
            "PolicyDocument": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": "*",
                        "Action": [
                            "dynamodb:GetItem",
                            "dynamodb:PutItem",
                            "dynamodb:DeleteItem",
                            "dynamodb:UpdateItem",
                        ],
                        "Resource": [
                            attr("AuthTable", "Arn"),
                            sub(
                                "arn:${AWS::Partition}:dynamodb:${AWS::Region}:${AWS::AccountId}:table/${GpuStateTableName}"
                            ),
                        ],
                    }
                ],
            },
        },
    )
    add(
        "LogGroup",
        "Logs::LogGroup",
        {
            "LogGroupName": sub("/ecs/${AWS::StackName}"),
            "RetentionInDays": 14,
        },
        DeletionPolicy="Retain",
        UpdateReplacePolicy="Retain",
    )
    trust = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "ecs-tasks.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    }
    add(
        "ExecutionRole",
        "IAM::Role",
        {
            "AssumeRolePolicyDocument": trust,
            "Policies": [
                {
                    "PolicyName": "PullImagesAndWriteLogs",
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
                                "Resource": [
                                    attr("ApiRepository", "Arn"),
                                    attr("ModelRepository", "Arn"),
                                ],
                            },
                            {
                                "Effect": "Allow",
                                "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
                                "Resource": attr("LogGroup", "Arn"),
                            },
                        ],
                    },
                }
            ],
        },
    )
    add(
        "TaskRole",
        "IAM::Role",
        {
            "AssumeRolePolicyDocument": trust,
            "Policies": [
                {
                    "PolicyName": "AuthenticationStore",
                    "PolicyDocument": {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Action": [
                                    "dynamodb:GetItem",
                                    "dynamodb:PutItem",
                                    "dynamodb:DeleteItem",
                                    "dynamodb:UpdateItem",
                                ],
                                "Resource": [
                                    attr("AuthTable", "Arn"),
                                    sub(
                                        "arn:${AWS::Partition}:dynamodb:${AWS::Region}:${AWS::AccountId}:table/${GpuStateTableName}"
                                    ),
                                ],
                            },
                            {
                                "Effect": "Allow",
                                "Action": "sagemaker:InvokeEndpoint",
                                "Resource": sub(
                                    "arn:${AWS::Partition}:sagemaker:${AWS::Region}:${AWS::AccountId}:endpoint/${AWS::StackName}-decider"
                                ),
                            },
                            {
                                "Effect": "Allow",
                                "Action": "bedrock:InvokeModel",
                                "Resource": bedrock_resources,
                            },
                            {
                                "Effect": "Allow",
                                "Action": "bedrock:InvokeModel",
                                "Resource": routing_resources,
                            },
                        ],
                    },
                }
            ],
        },
    )
    add("Cluster", "ECS::Cluster", {"ClusterName": sub("${AWS::StackName}")})

    add(
        "JevLogGroup",
        "Logs::LogGroup",
        {"LogGroupName": sub("/aws/lambda/${AWS::StackName}-jev"), "RetentionInDays": 14},
        Condition="HasJev",
    )
    add(
        "JevRole",
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
                    "PolicyName": "JevSecretAndLogs",
                    "PolicyDocument": {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Action": "secretsmanager:GetSecretValue",
                                "Resource": ref("JevSecretArn"),
                            },
                            {
                                "Effect": "Allow",
                                "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
                                "Resource": attr("JevLogGroup", "Arn"),
                            },
                        ],
                    },
                }
            ],
        },
        Condition="HasJev",
    )
    add(
        "JevFunction",
        "Lambda::Function",
        {
            "FunctionName": sub("${AWS::StackName}-jev"),
            "Runtime": "python3.12",
            "Handler": "index.handler",
            "Architectures": ["arm64"],
            "MemorySize": 256,
            "Timeout": 40,
            "Role": attr("JevRole", "Arn"),
            "Environment": {"Variables": {"JEV_SECRET_ARN": ref("JevSecretArn")}},
            "Code": {"ZipFile": Path(__file__).with_name("jev_proxy.py").read_text()},
        },
        Condition="HasJev",
    )
    add(
        "JevInvokePolicy",
        "IAM::Policy",
        {
            "PolicyName": "InvokeJevBridge",
            "Roles": [ref("TaskRole")],
            "PolicyDocument": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": "lambda:InvokeFunction",
                        "Resource": attr("JevFunction", "Arn"),
                    }
                ],
            },
        },
        Condition="HasJev",
    )
    add(
        "LambdaEndpoint",
        "EC2::VPCEndpoint",
        {
            "VpcId": ref("Vpc"),
            "VpcEndpointType": "Interface",
            "PrivateDnsEnabled": True,
            "ServiceName": sub("com.amazonaws.${AWS::Region}.lambda"),
            "SubnetIds": [ref("Subnet1")],
            "SecurityGroupIds": [ref("EndpointSecurityGroup")],
            "PolicyDocument": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": "*",
                        "Action": "lambda:InvokeFunction",
                        "Resource": attr("JevFunction", "Arn"),
                        "Condition": {"ArnEquals": {"aws:PrincipalArn": attr("TaskRole", "Arn")}},
                    }
                ],
            },
        },
        Condition="HasJev",
    )

    # Reuse the existing same-region VPC peering; expose only the model port to this API.
    add(
        "VllmRoute",
        "EC2::Route",
        {
            "RouteTableId": ref("PrivateRoutes"),
            "DestinationCidrBlock": sub("${VllmPrivateIp}/32"),
            "VpcPeeringConnectionId": ref("VllmPeeringConnectionId"),
        },
        Condition="HasVllm",
    )
    for n in (1, 2):
        add(
            f"VllmReturnRoute{n}",
            "EC2::Route",
            {
                "RouteTableId": ref("VllmRouteTableId"),
                "DestinationCidrBlock": f"10.78.{n}.0/24",
                "VpcPeeringConnectionId": ref("VllmPeeringConnectionId"),
            },
            Condition="HasVllm",
        )
    add(
        "VllmApiIngress",
        "EC2::SecurityGroupIngress",
        {
            "GroupId": ref("VllmSecurityGroupId"),
            "IpProtocol": "tcp",
            "FromPort": 8100,
            "ToPort": 8100,
            "SourceSecurityGroupId": ref("TaskSecurityGroup"),
            "Description": "Authenticated System One calls from the Decider demo API",
        },
        Condition="HasVllm",
    )
    add(
        "VllmSecretPolicy",
        "IAM::Policy",
        {
            "PolicyName": "ReadVllmApiKey",
            "Roles": [ref("ExecutionRole")],
            "PolicyDocument": {
                "Version": "2012-10-17",
                "Statement": [{
                    "Effect": "Allow", "Action": "secretsmanager:GetSecretValue",
                    "Resource": ref("VllmSecretArn"),
                }],
            },
        },
        Condition="HasVllm",
    )
    add(
        "SecretsManagerEndpoint",
        "EC2::VPCEndpoint",
        {
            "VpcId": ref("Vpc"), "VpcEndpointType": "Interface", "PrivateDnsEnabled": True,
            "ServiceName": sub("com.amazonaws.${AWS::Region}.secretsmanager"),
            "SubnetIds": [ref("Subnet1")],
            "SecurityGroupIds": [ref("EndpointSecurityGroup")],
            "PolicyDocument": {
                "Version": "2012-10-17",
                "Statement": [{
                    "Effect": "Allow", "Principal": "*",
                    "Action": "secretsmanager:GetSecretValue",
                    "Resource": ref("VllmSecretArn"),
                    "Condition": {"ArnEquals": {"aws:PrincipalArn": attr("ExecutionRole", "Arn")}},
                }],
            },
        },
        Condition="HasVllm",
    )

    def logging(prefix):
        return {
            "LogDriver": "awslogs",
            "Options": {
                "awslogs-group": ref("LogGroup"),
                "awslogs-region": ref("AWS::Region"),
                "awslogs-stream-prefix": prefix,
                "mode": "non-blocking",
                "max-buffer-size": "5m",
            },
        }

    def healthcheck(url, start):
        return {
            "Command": [
                "CMD-SHELL",
                f"python -c \"import urllib.request; urllib.request.urlopen('{url}', timeout=3)\"",
            ],
            "Interval": 30,
            "Timeout": 5,
            "Retries": 3,
            "StartPeriod": start,
        }

    add(
        "TaskDefinition",
        "ECS::TaskDefinition",
        {
            "Family": sub("${AWS::StackName}"),
            "Cpu": "256",
            "Memory": "512",
            "RuntimePlatform": {"CpuArchitecture": "ARM64", "OperatingSystemFamily": "LINUX"},
            "RequiresCompatibilities": ["FARGATE"],
            "NetworkMode": "awsvpc",
            "ExecutionRoleArn": attr("ExecutionRole", "Arn"),
            "TaskRoleArn": attr("TaskRole", "Arn"),
            "ContainerDefinitions": [
                {
                    "Name": "api",
                    "Image": {
                        "Fn::If": [
                            "HasApiImageTag",
                            sub("${ApiRepository.RepositoryUri}:${ApiImageTag}"),
                            sub("${ApiRepository.RepositoryUri}:${ImageTag}"),
                        ]
                    },
                    "Essential": True,
                    "Cpu": 256,
                    "Memory": 512,
                    "User": "10001",
                    "ReadonlyRootFilesystem": True,
                    "StopTimeout": 60,
                    "StartTimeout": 120,
                    "PortMappings": [{"ContainerPort": 8000, "Protocol": "tcp"}],
                    "Environment": [
                        {"Name": "SERVE_FRONTEND", "Value": "false"},
                        {"Name": "STRANDS_DECIDER_URL", "Value": {
                            "Fn::If": ["HasVllm", sub("http://${VllmPrivateIp}:8100"),
                                       "http://127.0.0.1:8099"]
                        }},
                        {"Name": "GPU_STATE_TABLE", "Value": {
                            "Fn::If": ["HasVllm", "", ref("GpuStateTableName")]
                        }},
                        {"Name": "GPU_PROVIDER", "Value": ref("ModelProvider")},
                        {"Name": "VLLM_INSTANCE_ID", "Value": ref("VllmInstanceId")},
                        {"Name": "BEDROCK_ENABLED", "Value": "true"},
                        {
                            "Name": "JEV_FUNCTION_NAME",
                            "Value": {"Fn::If": ["HasJev", attr("JevFunction", "Arn"), ""]},
                        },
                        {"Name": "GPU_MANAGERS", "Value": "admin"},
                        {"Name": "DECIDER_TIMEOUT", "Value": "50"},
                        {"Name": "AUTH_TABLE", "Value": ref("AuthTable")},
                        {"Name": "AWS_REGION", "Value": ref("AWS::Region")},
                        {"Name": "AUTH_COOKIE_SECURE", "Value": "true"},
                        {"Name": "AUTH_ORIGIN", "Value": sub("https://${Distribution.DomainName}")},
                    ],
                    "Secrets": {"Fn::If": [
                        "HasVllm",
                        [{"Name": "DECIDER_API_KEY", "ValueFrom": sub("${VllmSecretArn}:api_key::")}],
                        [],
                    ]},
                    "LogConfiguration": logging("api"),
                    "HealthCheck": healthcheck("http://127.0.0.1:8000/api/live", 10),
                },
            ],
        },
    )
    add(
        "LoadBalancer",
        "ElasticLoadBalancingV2::LoadBalancer",
        {
            "Scheme": "internal",
            "Type": "application",
            "IpAddressType": "ipv4",
            "Subnets": subnets,
            "SecurityGroups": [ref("AlbSecurityGroup")],
            "LoadBalancerAttributes": [
                {"Key": "idle_timeout.timeout_seconds", "Value": "65"},
                {"Key": "routing.http.drop_invalid_header_fields.enabled", "Value": "true"},
            ],
        },
    )
    add(
        "TargetGroup",
        "ElasticLoadBalancingV2::TargetGroup",
        {
            "VpcId": ref("Vpc"),
            "Protocol": "HTTP",
            "Port": 8000,
            "TargetType": "ip",
            "HealthCheckPath": "/api/ready",
            "HealthCheckIntervalSeconds": 30,
            "HealthCheckTimeoutSeconds": 5,
            "HealthyThresholdCount": 2,
            "UnhealthyThresholdCount": 3,
            "Matcher": {"HttpCode": "200"},
            "TargetGroupAttributes": [
                {"Key": "deregistration_delay.timeout_seconds", "Value": "60"}
            ],
        },
    )
    add(
        "Listener",
        "ElasticLoadBalancingV2::Listener",
        {
            "LoadBalancerArn": ref("LoadBalancer"),
            "Port": 80,
            "Protocol": "HTTP",
            "DefaultActions": [{"Type": "forward", "TargetGroupArn": ref("TargetGroup")}],
        },
    )
    add(
        "Service",
        "ECS::Service",
        {
            "ServiceName": sub("${AWS::StackName}"),
            "Cluster": ref("Cluster"),
            "TaskDefinition": ref("TaskDefinition"),
            "DesiredCount": ref("DesiredCount"),
            "LaunchType": "FARGATE",
            "PlatformVersion": "LATEST",
            "DeploymentConfiguration": {
                "MinimumHealthyPercent": 100,
                "MaximumPercent": 200,
                "DeploymentCircuitBreaker": {"Enable": True, "Rollback": True},
            },
            "HealthCheckGracePeriodSeconds": 360,
            "NetworkConfiguration": {
                "AwsvpcConfiguration": {
                    "AssignPublicIp": "DISABLED",
                    "Subnets": subnets,
                    "SecurityGroups": [ref("TaskSecurityGroup")],
                }
            },
            "LoadBalancers": [
                {
                    "ContainerName": "api",
                    "ContainerPort": 8000,
                    "TargetGroupArn": ref("TargetGroup"),
                }
            ],
        },
        DependsOn=[
            "Listener",
            "EcrApiEndpoint",
            "EcrDockerEndpoint",
            "LogsEndpoint",
            "S3Endpoint",
            "DynamoEndpoint",
        ],
    )
    add(
        "VpcOrigin",
        "CloudFront::VpcOrigin",
        {
            "VpcOriginEndpointConfig": {
                "Name": sub("${AWS::StackName}-${AWS::Region}-api"),
                "Arn": ref("LoadBalancer"),
                "HTTPPort": 80,
                "HTTPSPort": 443,
                "OriginProtocolPolicy": "http-only",
                "OriginSSLProtocols": ["TLSv1.2"],
            },
        },
        DependsOn=["GatewayAttachment", "Listener"],
    )
    add(
        "FrontendBucket",
        "S3::Bucket",
        {
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True,
                "BlockPublicPolicy": True,
                "IgnorePublicAcls": True,
                "RestrictPublicBuckets": True,
            },
            "OwnershipControls": {"Rules": [{"ObjectOwnership": "BucketOwnerEnforced"}]},
            "BucketEncryption": {
                "ServerSideEncryptionConfiguration": [
                    {"ServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}
                ]
            },
            "VersioningConfiguration": {"Status": "Enabled"},
        },
        DeletionPolicy="Retain",
        UpdateReplacePolicy="Retain",
    )
    add(
        "OriginAccessControl",
        "CloudFront::OriginAccessControl",
        {
            "OriginAccessControlConfig": {
                "Name": sub("${AWS::StackName}-${AWS::Region}-s3-oac"),
                "OriginAccessControlOriginType": "s3",
                "SigningBehavior": "always",
                "SigningProtocol": "sigv4",
            },
        },
    )
    add(
        "StaticCachePolicy",
        "CloudFront::CachePolicy",
        {
            "CachePolicyConfig": {
                "Name": sub("${AWS::StackName}-${AWS::Region}-static"),
                "DefaultTTL": 300,
                "MinTTL": 0,
                "MaxTTL": 86400,
                "ParametersInCacheKeyAndForwardedToOrigin": {
                    "CookiesConfig": {"CookieBehavior": "none"},
                    "HeadersConfig": {"HeaderBehavior": "none"},
                    "QueryStringsConfig": {"QueryStringBehavior": "none"},
                    "EnableAcceptEncodingGzip": True,
                    "EnableAcceptEncodingBrotli": True,
                },
            }
        },
    )
    add(
        "Distribution",
        "CloudFront::Distribution",
        {
            "DistributionConfig": {
                "Enabled": True,
                "Comment": sub("${AWS::StackName}: private S3 + ECS"),
                "DefaultRootObject": "index.html",
                "HttpVersion": "http2and3",
                "IPV6Enabled": True,
                "PriceClass": "PriceClass_All",
                "ViewerCertificate": {"CloudFrontDefaultCertificate": True},
                "Origins": [
                    {
                        "Id": "frontend",
                        "DomainName": attr("FrontendBucket", "RegionalDomainName"),
                        "OriginAccessControlId": ref("OriginAccessControl"),
                        "S3OriginConfig": {"OriginAccessIdentity": ""},
                    },
                    {
                        "Id": "api",
                        "DomainName": attr("LoadBalancer", "DNSName"),
                        "VpcOriginConfig": {
                            "VpcOriginId": attr("VpcOrigin", "Id"),
                            "OriginReadTimeout": 60,
                            "OriginKeepaliveTimeout": 5,
                        },
                        "ConnectionAttempts": 1,
                        "ConnectionTimeout": 10,
                    },
                ],
                "DefaultCacheBehavior": {
                    "TargetOriginId": "frontend",
                    "ViewerProtocolPolicy": "redirect-to-https",
                    "AllowedMethods": ["GET", "HEAD"],
                    "CachedMethods": ["GET", "HEAD"],
                    "Compress": True,
                    "CachePolicyId": ref("StaticCachePolicy"),
                    "ResponseHeadersPolicyId": "67f7725c-6f97-4210-82d7-5512b31e9d03",
                },
                "CacheBehaviors": [
                    {
                        "PathPattern": "/api/*",
                        "TargetOriginId": "api",
                        "ViewerProtocolPolicy": "https-only",
                        "AllowedMethods": [
                            "GET",
                            "HEAD",
                            "OPTIONS",
                            "PUT",
                            "PATCH",
                            "POST",
                            "DELETE",
                        ],
                        "CachedMethods": ["GET", "HEAD"],
                        "Compress": True,
                        "CachePolicyId": "4135ea2d-6df8-44a3-9df3-4b5a84be39ad",
                        "OriginRequestPolicyId": "b689b0a8-53d0-40ab-baf2-68738e2966ac",
                        "ResponseHeadersPolicyId": "67f7725c-6f97-4210-82d7-5512b31e9d03",
                    }
                ],
                "CustomErrorResponses": [
                    {"ErrorCode": code, "ErrorCachingMinTTL": 0}
                    for code in [403, 404, 500, 502, 503, 504]
                ],
            }
        },
    )
    add(
        "FrontendBucketPolicy",
        "S3::BucketPolicy",
        {
            "Bucket": ref("FrontendBucket"),
            "PolicyDocument": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "AllowThisCloudFrontDistribution",
                        "Effect": "Allow",
                        "Principal": {"Service": "cloudfront.amazonaws.com"},
                        "Action": "s3:GetObject",
                        "Resource": sub("${FrontendBucket.Arn}/*"),
                        "Condition": {
                            "StringEquals": {
                                "AWS:SourceArn": sub(
                                    "arn:${AWS::Partition}:cloudfront::${AWS::AccountId}:distribution/${Distribution}"
                                )
                            }
                        },
                    },
                    {
                        "Sid": "DenyInsecureTransport",
                        "Effect": "Deny",
                        "Principal": "*",
                        "Action": "s3:*",
                        "Resource": [attr("FrontendBucket", "Arn"), sub("${FrontendBucket.Arn}/*")],
                        "Condition": {"Bool": {"aws:SecureTransport": "false"}},
                    },
                ],
            },
        },
    )
    outputs = {
        "WebsiteUrl": sub("https://${Distribution.DomainName}"),
        "DistributionId": ref("Distribution"),
        "FrontendBucketName": ref("FrontendBucket"),
        "ApiRepositoryUri": attr("ApiRepository", "RepositoryUri"),
        "ModelRepositoryUri": attr("ModelRepository", "RepositoryUri"),
        "ClusterName": ref("Cluster"),
        "ServiceName": attr("Service", "Name"),
        "TargetGroupArn": ref("TargetGroup"),
        "VpcId": ref("Vpc"),
        "LogGroupName": ref("LogGroup"),
        "AuthTableName": ref("AuthTable"),
    }
    return {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Description": "Strands Decider: private S3/OAC, internal ALB, small ARM64 Fargate API with a separately managed reusable On-Demand GPU.",
        "Parameters": {
            "ImageTag": {"Type": "String", "AllowedPattern": "[A-Za-z0-9._-]+"},
            "ApiImageTag": {"Type": "String", "Default": "", "AllowedPattern": "[A-Za-z0-9._-]*"},
            "GpuStateTableName": {"Type": "String", "AllowedPattern": "[A-Za-z0-9._-]+"},
            "ModelProvider": {
                "Type": "String",
                "Default": "ec2",
                "AllowedValues": ["ec2", "sagemaker", "vllm"],
            },
            **{name: {"Type": "String", "Default": ""} for name in (
                "VllmPrivateIp", "VllmSecretArn", "VllmInstanceId", "VllmSecurityGroupId",
                "VllmRouteTableId", "VllmPeeringConnectionId",
            )},
            "JevSecretArn": {
                "Type": "String",
                "Default": "",
                "Description": "Optional Secrets Manager ARN containing the Jev API key (not the key itself).",
            },
            "DesiredCount": {"Type": "Number", "Default": 0, "MinValue": 0, "MaxValue": 4},
            "AvailabilityZone1": {"Type": "AWS::EC2::AvailabilityZone::Name"},
            "AvailabilityZone2": {"Type": "AWS::EC2::AvailabilityZone::Name"},
            "CloudFrontPrefixListId": {"Type": "String"},
        },
        "Conditions": {
            "HasApiImageTag": {"Fn::Not": [{"Fn::Equals": [ref("ApiImageTag"), ""]}]},
            "HasJev": {"Fn::Not": [{"Fn::Equals": [ref("JevSecretArn"), ""]}]},
            "HasVllm": {"Fn::Equals": [ref("ModelProvider"), "vllm"]},
        },
        "Resources": resources,
        "Outputs": {key: {"Value": value} for key, value in outputs.items()},
    }


if __name__ == "__main__":
    output = Path(__file__).with_name("cloudformation.json")
    output.write_text(json.dumps(template(), indent=2) + "\n")
    print(output)
