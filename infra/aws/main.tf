# VoiceDesk on AWS: Lambda (Python 3.12) behind a Lambda function URL, call insights on Amazon Bedrock
# (Amazon Nova Micro), CloudWatch logs with short retention, and a 1 USD budget alert. Sized for the
# AWS Free plan / always-free Lambda allowance (1M requests and 400k GB-seconds a month).
terraform {
  required_version = ">= 1.6"
  required_providers {
    aws     = { source = "hashicorp/aws", version = "~> 6.0" }
    archive = { source = "hashicorp/archive", version = "~> 2.5" }
  }
}

provider "aws" {
  region = var.region
  default_tags { tags = { project = "voicedesk", managed_by = "terraform" } }
}

data "aws_caller_identity" "me" {}

data "archive_file" "bundle" {
  type        = "zip"
  source_dir  = "${path.module}/build"
  output_path = "${path.module}/voicedesk-lambda.zip"
}

# ---- IAM: logs + one Bedrock model, nothing else ----
resource "aws_iam_role" "lambda" {
  name = "voicedesk-lambda"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy_attachment" "logs" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "bedrock" {
  name = "invoke-one-model"
  role = aws_iam_role.lambda.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["bedrock:InvokeModel", "bedrock:Converse"]
      Resource = ["arn:aws:bedrock:${var.region}::foundation-model/${var.bedrock_model_id}"]
    }]
  })
}

resource "aws_cloudwatch_log_group" "fn" {
  name              = "/aws/lambda/voicedesk"
  retention_in_days = 3
}

# ---- the function ----
resource "aws_lambda_function" "voicedesk" {
  function_name    = "voicedesk"
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.12"
  architectures    = ["x86_64"]
  handler          = "lambda_handler.handler"
  filename         = data.archive_file.bundle.output_path
  source_code_hash = data.archive_file.bundle.output_base64sha256
  memory_size      = 512
  timeout          = 30
  environment {
    variables = {
      VOICEDESK_DB       = "/tmp/voicedesk.db"
      BEDROCK_MODEL_ID   = var.bedrock_model_id
      INSIGHTS_DAILY_CAP = tostring(var.insights_daily_cap)
    }
  }
  depends_on = [aws_cloudwatch_log_group.fn, aws_iam_role_policy_attachment.logs]
}

resource "aws_lambda_function_url" "public" {
  function_name      = aws_lambda_function.voicedesk.function_name
  authorization_type = "NONE"
}

# Public function URLs need both permissions (AWS requirement since Oct 2025).
resource "aws_lambda_permission" "url_invoke" {
  statement_id           = "public-function-url"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.voicedesk.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

resource "aws_lambda_permission" "url_invoke_fn" {
  statement_id             = "public-function-url-invoke"
  action                   = "lambda:InvokeFunction"
  function_name            = aws_lambda_function.voicedesk.function_name
  principal                = "*"
  invoked_via_function_url = true
}

# ---- cost guard ----
resource "aws_budgets_budget" "one_dollar" {
  name         = "voicedesk-1-usd"
  budget_type  = "COST"
  limit_amount = "1"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 1
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.alert_email]
  }
}
