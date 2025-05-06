import yaml
from main import app  # Import your FastAPI app

# Generate the OpenAPI schema
openapi_schema = app.openapi()

# Force OpenAPI version to 3.0.0
openapi_schema["openapi"] = "3.0.0"

# Add a custom info section
openapi_schema["info"] = {
    "title": "OghmAI API",
    "description": "API for the OghmAI vocabulary app",
    "version": "1.0.0"
}

# Add API Key security scheme
openapi_schema.setdefault("components", {}).setdefault("securitySchemes", {})
openapi_schema["components"]["securitySchemes"]["CognitoAuthorizer"] = {
    "type": "apiKey",
    "name": "Authorization",
    "in": "header",
    "x-amazon-apigateway-authtype" : "cognito_user_pools",
    "x-amazon-apigateway-authorizer": {
        "type": "cognito_user_pools",
        "providerARNs": [
            "${cognito_user_pool_arn}"  # Replace this when deploying
        ]
    }
}

# Add security and integration to each method
for path, methods in openapi_schema["paths"].items():
    for method, details in methods.items():
        # Add Cognito security requirement
        details["security"] = [{"CognitoAuthorizer": []}]

        # Add x-amazon-apigateway-integration
        details["x-amazon-apigateway-integration"] = {
            "uri": "${lambda_arn}",
            "httpMethod": "POST",
            "type": "aws_proxy"
        }

        # Simplify responses
        if "responses" in details:
            for status_code, response in details["responses"].items():
                response["content"] = {
                    "application/json": {}
                }



# Save the schema to a YAML file
with open("openapi.yaml", "w") as f:
    yaml.dump(openapi_schema, f, default_flow_style=False)

print("OpenAPI schema has been generated and saved to openapi.yaml")