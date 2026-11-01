"""Add optional AC LoRA connectivity to an existing application template."""


def add_ac_control(document):
    document["Parameters"].update({
        "AcLoraUrl": {"Type": "String", "Default": "",
                      "Description": "Private authenticated Liquid LoRA gateway URL"},
        "AcLoraSecretArn": {"Type": "String", "Default": "",
                            "Description": "Secrets Manager ARN containing the LoRA gateway token"},
    })
    document.setdefault("Conditions", {})["HasAcLora"] = {
        "Fn::And": [
            {"Fn::Not": [{"Fn::Equals": [{"Ref": name}, ""]}]}
            for name in ("AcLoraUrl", "AcLoraSecretArn")
        ]
    }
    resources = document["Resources"]
    api = resources["TaskDefinition"]["Properties"]["ContainerDefinitions"][0]
    api["Environment"].append({"Name": "AC_LORA_URL", "Value": {"Ref": "AcLoraUrl"}})
    secret = {"Fn::If": [
        "HasAcLora", {"Name": "AC_LORA_TOKEN", "ValueFrom": {"Ref": "AcLoraSecretArn"}},
        {"Ref": "AWS::NoValue"},
    ]}
    existing = api.setdefault("Secrets", [])
    if isinstance(existing, dict):
        for branch in existing["Fn::If"][1:]:
            branch.append(secret)
    else:
        existing.append(secret)
    resources["ExecutionRole"]["Properties"]["Policies"].append({"Fn::If": [
        "HasAcLora", {
            "PolicyName": "ACLiquidLoraReadSecret",
            "PolicyDocument": {"Version": "2012-10-17", "Statement": [{
                "Effect": "Allow", "Action": ["secretsmanager:GetSecretValue"],
                "Resource": {"Ref": "AcLoraSecretArn"},
            }]},
        }, {"Ref": "AWS::NoValue"},
    ]})
    statement = resources["SecretsManagerEndpoint"]["Properties"]["PolicyDocument"]["Statement"][0]
    previous = statement["Resource"]
    statement["Resource"] = {"Fn::If": [
        "HasAcLora", [previous, {"Ref": "AcLoraSecretArn"}], previous,
    ]}
    return document
