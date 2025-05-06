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
# DynamoDB Recycle Bin Table
#############################
resource "aws_dynamodb_table" "recycle_bin" {
  name           = "oghmai_vocabulary_recycle_bin"
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

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }
}

#############################
# DynamoDB Challenge Cache
#############################
resource "aws_dynamodb_table" "challenge_table" {
  name           = "oghmai_challenges"
  billing_mode   = "PROVISIONED"
  read_capacity  = 1
  write_capacity = 1
  hash_key       = "user_id"
  range_key      = "challenge_id"

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "challenge_id"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
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

# TODO: Built by CI/CD pipeline, this is kind of a pain point now and should be automated better
resource "aws_lambda_layer_version" "oghmai_layer" {
  filename            = "../layers/oghmai_layer.zip"
  layer_name          = "oghmai-layer"
  compatible_runtimes = ["python3.11"]
  description         = "Basic OghmAI layer with FastAPI and Mangum dependencies."
  source_code_hash    = filebase64sha256("../lambda/requirements.txt")
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
  body = templatefile("openapi.yaml", {
    lambda_arn = aws_lambda_function.api_handler.invoke_arn
    cognito_user_pool_arn = aws_cognito_user_pool.oghmai_user_pool.arn
  })
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
  depends_on  = [aws_api_gateway_rest_api.oghmai_api]
  rest_api_id = aws_api_gateway_rest_api.oghmai_api.id

  lifecycle {
    create_before_destroy = true
  }

  triggers = {
    always_deploy = timestamp()
  }
}

#############################
# Cognito User Pool
#############################
resource "aws_cognito_user_pool" "oghmai_user_pool" {
  name = "oghmai-user-pool"

  password_policy {
    minimum_length    = 8
    require_numbers   = true
    require_uppercase = true
    require_lowercase = true
    require_symbols   = false
  }

  mfa_configuration = "OFF"

  auto_verified_attributes = ["email"]
}

#############################
# Cognito App Client (Android)
#############################
resource "aws_cognito_user_pool_client" "oghmai_android_client" {
  name                                 = "oghmai-android-client"
  user_pool_id                         = aws_cognito_user_pool.oghmai_user_pool.id
  generate_secret                      = false
  allowed_oauth_flows                  = ["code", "implicit"]
  allowed_oauth_scopes                 = ["email", "openid", "profile"]
  enable_token_revocation              = true
  prevent_user_existence_errors        = "ENABLED"
  allowed_oauth_flows_user_pool_client = true
  callback_urls                        = ["net.gask13.oghmai://callback"] # Replace with your app's callback URL
  logout_urls                          = ["net.gask13.oghmai://logout"]   # Replace with your app's logout URL
  refresh_token_validity               = 30                               # Days
  access_token_validity                = 1                            # Hours
  id_token_validity                    = 1                            # Hours
  explicit_auth_flows                  = ["ALLOW_REFRESH_TOKEN_AUTH", "ALLOW_USER_SRP_AUTH", "ALLOW_USER_PASSWORD_AUTH"]
}

#############################
# Update Lambda permissions to allow Cognito claims in the event
#############################
resource "aws_lambda_permission" "allow_apigw_with_cognito" {
  statement_id  = "AllowExecutionFromAPIGatewayWithCognito"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api_handler.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.oghmai_api.execution_arn}/*/*"
}

#############################
# Outputs
#############################

# Empty, we do not copy it anywhere and it is safer to check in console / get it in the other app build :)