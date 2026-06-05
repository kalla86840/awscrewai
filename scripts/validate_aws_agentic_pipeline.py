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

    require("kalla86840/awscrewai" in cicd_template, "CodePipeline source must point to kalla86840/awscrewai.")
    require("agentic-open-ai-crewai-endpoint" in cicd_template, "ECR repository default must use the CrewAI endpoint name.")
    require("${ProjectName}-crewai-endpoint" in endpoint_template, "Lambda function name must match the CodeBuild smoke test.")
    require("--function-name \"${PROJECT_NAME}-crewai-endpoint\"" in buildspec, "CodeBuild must invoke the deployed CrewAI Lambda.")
    require('"orchestrator":"crewai"' in buildspec, "Endpoint metadata must identify the CrewAI orchestrator.")
    require("crewai" in requirements.lower(), "Endpoint container must install CrewAI.")
    require("autogen" not in requirements.lower(), "Endpoint container requirements must not install AutoGen.")

    print("AWS CrewAI CodePipeline validation passed.")


if __name__ == "__main__":
    main()
