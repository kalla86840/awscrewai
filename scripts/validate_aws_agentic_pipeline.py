from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def require(condition, message):
    if not condition:
        raise SystemExit(message)


def main():
    buildspec = read("buildspec-agentic.yml")
    cicd_template = read("infrastructure/agentic-cicd.yaml")
    endpoint_template = read("infrastructure/agentic-endpoint.yaml")
    requirements = read("agentic_endpoint/requirements.txt")

    require("aws-open-ai-crewai" in buildspec, "Buildspec PROJECT_NAME must match the requested pipeline name.")
    require("Default: aws-open-ai-crewai" in cicd_template, "CodePipeline ProjectName default must match the requested pipeline name.")
    require("Default: aws-open-ai-crewai" in endpoint_template, "Endpoint ProjectName default must match the requested endpoint name.")
    require("kalla86840/awscrewai" in cicd_template, "CodePipeline source must point to kalla86840/awscrewai.")
    require("aws-open-ai-crewai-endpoint" in cicd_template, "ECR repository default must use the renamed pipeline prefix.")
    require("ECR_REPOSITORY_NAME" in buildspec, "Buildspec must be able to discover the ECR repository when the URI env var is missing.")
    require("aws ecr describe-repositories" in buildspec, "Buildspec must fall back to ECR repository lookup.")
    require("ECR_REPOSITORY_NAME" in cicd_template, "CodeBuild project must receive the ECR repository name.")
    require("FunctionName: !Ref ProjectName" in endpoint_template, "Lambda function name must match the requested endpoint name.")
    require("--function-name \"${PROJECT_NAME}\"" in buildspec, "CodeBuild must invoke the deployed Lambda.")
    require("Action: lambda:InvokeFunctionUrl" in endpoint_template, "Endpoint stack must allow Function URL invocation.")
    require("Action: lambda:InvokeFunction\n" not in endpoint_template, "Endpoint stack must not add a public lambda:InvokeFunction permission.")
    require("InvokedViaFunctionUrl: true" not in endpoint_template, "Endpoint stack must not add redundant Lambda invoke permission.")
    require("cloudformation:DescribeStackEvents" in cicd_template, "CodeBuild role must be able to print endpoint stack events.")
    require('"orchestrator":"crewai"' in buildspec, "Endpoint metadata must identify the CrewAI orchestrator.")
    require("crewai" in requirements.lower(), "Endpoint container must install CrewAI.")
    require("pinecone" not in requirements.lower(), "Endpoint container requirements must not install Pinecone for this OpenAI-only deploy.")
    require("autogen" not in requirements.lower(), "Endpoint container requirements must not install AutoGen.")
    require("Pinecone" not in cicd_template, "CodePipeline stack must not expose Pinecone parameters.")
    require("PINECONE" not in buildspec, "CodeBuild must not pass Pinecone settings.")
    require("PINECONE" not in endpoint_template, "Endpoint Lambda must not receive Pinecone settings.")
    require("news-demo" not in buildspec and "news-demo" not in cicd_template and "news-demo" not in endpoint_template, "Agentic pipeline must not depend on the old Pinecone index.")
    require("HasPineconeSecret" not in endpoint_template, "Endpoint stack must not include Pinecone conditions.")

    print("AWS OpenAI agentic CodePipeline validation passed.")


if __name__ == "__main__":
    main()
