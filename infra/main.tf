provider "aws" {
  region = "us-east-1" # Change as needed
}

terraform {
  backend "s3" {
    bucket  = "oghmai-terraform-state"
    key     = "env/dev/terraform.tfstate"
    region  = "us-east-1"
    encrypt = true
  }
}

#############################
# IAM Role for Lambda
#############################
resource "aws_iam_role" "lambda_exec_role" {
  name = "oghmai-lambda-vocab-exec-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Action = "sts:AssumeRole",
      Effect = "Allow",
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "lambda_custom_policy" {
  name = "oghmai-lambda-vocab-custom-policy"
  role = aws_iam_role.lambda_exec_role.id
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = [
          "dynamodb:*",
          "bedrock:*" # for future use
        ],
        Effect   = "Allow",
        Resource = "*"
      }
    ]
  })
}

#############################
# DynamoDB Table
#############################
resource "aws_dynamodb_table" "vocabulary" {
  name           = "oghmai_vocabulary_words"
  billing_mode   = "PROVISIONED"
  read_capacity  = 1
  write_capacity = 1
  hash_key       = "user_id"
  range_key      = "word"

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "word"
    type = "S"
  }
}

#############################
# Lambda Function
#############################
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "../lambda"
  output_path = "lambda.zip"
}

resource "aws_lambda_layer_version" "oghmai_layer" {
  filename            = "../layers/oghmai_layer.zip"
  layer_name          = "oghmai-layer"
  compatible_runtimes = ["python3.11"]
  description         = "Basic OghmAI layer with FastAPI and Mangum dependencies."
  source_code_hash    = filebase64sha256("../layers/oghmai_layer.zip")
}

resource "aws_lambda_function" "api_handler" {
  function_name    = "oghmai-vocab-api-handler"
  role             = aws_iam_role.lambda_exec_role.arn
  handler          = "main.handler"
  runtime          = "python3.11"
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  timeout          = 20 # Increase from default (3s) to allow for AI calls later
  memory_size      = 256
  publish          = true
  layers = [
    aws_lambda_layer_version.oghmai_layer.arn
  ]
}

#############################
# REST API Gateway
#############################
resource "aws_api_gateway_rest_api" "oghmai_api" {
  name        = "oghmai-vocab-rest-api"
  description = "OghmAI REST API for vocabulary app"
}

# Resource: /test
resource "aws_api_gateway_resource" "root" {
  rest_api_id = aws_api_gateway_rest_api.oghmai_api.id
  parent_id   = aws_api_gateway_rest_api.oghmai_api.root_resource_id
  path_part   = "test"
}

# Method: GET on "test"
resource "aws_api_gateway_method" "guess_get" {
  rest_api_id      = aws_api_gateway_rest_api.oghmai_api.id
  resource_id      = aws_api_gateway_resource.root.id
  http_method      = "GET"
  authorization    = "NONE"
  api_key_required = true
}

# Integration with Lambda (proxy)
resource "aws_api_gateway_integration" "lambda_integration" {
  rest_api_id             = aws_api_gateway_rest_api.oghmai_api.id
  resource_id             = aws_api_gateway_resource.root.id
  http_method             = aws_api_gateway_method.guess_get.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.api_handler.invoke_arn
}

# Lambda permission for API Gateway
resource "aws_lambda_permission" "allow_apigw" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api_handler.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.oghmai_api.execution_arn}/*/*"
}

resource "aws_api_gateway_stage" "oghmai_stage" {
  deployment_id = aws_api_gateway_deployment.oghmai_deployment.id
  rest_api_id   = aws_api_gateway_rest_api.oghmai_api.id
  stage_name    = "dev"
}

# Deployment
resource "aws_api_gateway_deployment" "oghmai_deployment" {
  depends_on  = [aws_api_gateway_integration.lambda_integration]
  rest_api_id = aws_api_gateway_rest_api.oghmai_api.id
}

#############################
# API Key + Usage Plan
#############################

resource "aws_api_gateway_api_key" "oghmai_dev_key" {
  name        = "OghmAI-Dev-Key"
  description = "API key for development use"
  enabled     = true
}

resource "aws_api_gateway_usage_plan" "oghmai_usage_plan" {
  name = "OghmAI-Dev-UsagePlan"

  api_stages {
    api_id = aws_api_gateway_rest_api.oghmai_api.id
    stage  = aws_api_gateway_stage.oghmai_stage.stage_name
  }

  throttle_settings {
    burst_limit = 10
    rate_limit  = 5
  }

  quota_settings {
    limit  = 100
    period = "WEEK"
  }
}

resource "aws_api_gateway_usage_plan_key" "oghmai_key_association" {
  key_id        = aws_api_gateway_api_key.oghmai_dev_key.id
  key_type      = "API_KEY"
  usage_plan_id = aws_api_gateway_usage_plan.oghmai_usage_plan.id
}

#############################
# Outputs
#############################

# Empty, we do not copy it anywhere and it is safer to check in console / get it in the other app build :)
