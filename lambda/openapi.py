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

# Rename schemas to remove hyphens
if "components" in openapi_schema and "schemas" in openapi_schema["components"]:
    updated_schemas = {}
    for schema_name, schema_content in openapi_schema["components"]["schemas"].items():
        # Replace hyphens with empty strings to make names alphanumeric
        new_schema_name = schema_name.replace("-", "")
        updated_schemas[new_schema_name] = schema_content

        # Update references in the paths
        for path, methods in openapi_schema["paths"].items():
            for method, details in methods.items():
                if "requestBody" in details and "schema" in details["requestBody"]["content"]["application/json"]:
                    ref = details["requestBody"]["content"]["application/json"]["schema"].get("$ref", "")
                    if ref.endswith(f"/{schema_name}"):
                        details["requestBody"]["content"]["application/json"]["schema"]["$ref"] = ref.replace(schema_name, new_schema_name)

                if "responses" in details:
                    for response in details["responses"].values():
                        if "content" in response and "application/json" in response["content"]:
                            schema = response["content"]["application/json"].get("schema", {})
                            if "$ref" in schema and schema["$ref"].endswith(f"/{schema_name}"):
                                schema["$ref"] = schema["$ref"].replace(schema_name, new_schema_name)

    # Replace the schemas in the components
    openapi_schema["components"]["schemas"] = updated_schemas

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