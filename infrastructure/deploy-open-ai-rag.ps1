param(
    [string]$StackName = "open-ai-rag-cicd",
    [string]$TemplateFile = "infrastructure/codepipeline.yaml",
    [string]$ProjectName = "open-ai-rag",
    [string]$ArtifactBucketName = "mlopswithsagemaker111",
    [string]$CodeStarConnectionArn = "arn:aws:codeconnections:us-west-1:659613508664:connection/4ea8863c-728d-450a-8752-251946939b36",
    [string]$RepositoryId = "kalla86840/awspineconeragforchatbotsandassistants",
    [string]$BranchName = "main",
    [string]$DeployEnvironment = "staging",
    # This secret must contain the OpenAI API key value, for example sk-...
    [string]$OpenAIApiKeySecretArn = "arn:aws:secretsmanager:us-west-1:659613508664:secret:openai/api-key-6BGXhJ",
    [string]$Region = "us-west-1"
)

aws cloudformation deploy `
    --region $Region `
    --template-file $TemplateFile `
    --stack-name $StackName `
    --capabilities CAPABILITY_NAMED_IAM `
    --parameter-overrides `
        ProjectName=$ProjectName `
        ArtifactBucketName=$ArtifactBucketName `
        CodeStarConnectionArn=$CodeStarConnectionArn `
        RepositoryId=$RepositoryId `
        BranchName=$BranchName `
        DeployEnvironment=$DeployEnvironment `
        OpenAIApiKeySecretArn=$OpenAIApiKeySecretArn

