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

##############################
# Endpoint definitions
##############################
locals {
  endpoints = {
    list_words = {
      method    = "GET"
      full_path = "words"
    }
    get_word = {
      method    = "GET"
      full_path = "word/{word}"
    }
    delete_word = {
      method    = "DELETE"
      full_path = "word/{word}"
    }
    describe_word = {
      method    = "POST"
      full_path = "describe-word"
    }
    save_word = {
      method    = "POST"
      full_path = "save-word"
    }
    words = {
      method    = "DELETE"
      full_path = "words"
    }
  }

  all_paths = distinct(flatten([
    for ep in local.endpoints : [
      for i in range(length(split("/", ep.full_path))) : join("/", slice(split("/", ep.full_path), 0, i + 1))
    ]
  ]))

  # Map from path to its parent
  path_map = {
    for p in local.all_paths :
    p => {
      path_part = regex("[^/]+$", p)
      parent    = length(split("/", p)) > 1 ? join("/", slice(split("/", p), 0, length(split("/", p)) - 1)) : null
    }
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
}

resource "aws_api_gateway_resource" "resources" {
  for_each    = local.path_map
  rest_api_id = aws_api_gateway_rest_api.oghmai_api.id
  parent_id   = each.value.parent != null ? (aws_api_gateway_resource.resources[each.value.parent].id) : aws_api_gateway_rest_api.oghmai_api.root_resource_id
  path_part   = each.value.path_part
}

resource "aws_api_gateway_method" "methods" {
  for_each = {
    for ep in local.endpoints :
    "${ep.full_path}_${ep.method}" => ep
  }

  rest_api_id      = aws_api_gateway_rest_api.oghmai_api.id
  resource_id      = aws_api_gateway_resource.resources[each.value.full_path].id
  http_method      = each.value.method
  authorization    = "NONE"
  api_key_required = each.value.api_key_required
}

resource "aws_api_gateway_integration" "integrations" {
  for_each                = aws_api_gateway_method.methods
  rest_api_id             = each.value.rest_api_id
  resource_id             = each.value.resource_id
  http_method             = each.value.http_method
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
  depends_on  = [aws_api_gateway_integration.integrations]
  rest_api_id = aws_api_gateway_rest_api.oghmai_api.id

  lifecycle {
    create_before_destroy = true
  }

  triggers = {
    always_deploy = timestamp()
  }
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
    limit  = 1000
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
