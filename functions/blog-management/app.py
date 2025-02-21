import json
import boto3
import os
import uuid
from datetime import datetime
from boto3.dynamodb.conditions import Key, Attr
import logging
import decimal

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['BLOGS_TABLE'])

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def decimal_default(obj):
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    raise TypeError("Type not serializable")

def create_blog(user_id, body):
    blog_id = str(uuid.uuid4())
    timestamp = datetime.now().isoformat()
    
    item = {
        'user_id': user_id,
        'blog_id': blog_id,
        'title': body.get('title'),
        'description': body.get('description'),
        'created_at': timestamp,
        'photoCount': 0
    }
    
    table.put_item(Item=item)
    return item

def get_user_blogs(user_id):
    response = table.query(
        KeyConditionExpression=Key('user_id').eq(user_id)
    )
    return response['Items']

def get_blog(user_id, blog_id):
    response = table.get_item(
        Key={
            'user_id': user_id,
            'blog_id': blog_id
        }
    )
    return response.get('Item')

def update_blog(user_id, blog_id, body):
    update_expression = 'SET '
    expression_attribute_values = {}
    
    if 'title' in body:
        update_expression += 'title = :title, '
        expression_attribute_values[':title'] = body['title']
    
    if 'description' in body:
        update_expression += 'description = :description, '
        expression_attribute_values[':description'] = body['description']
    
    # Remove trailing comma and space
    update_expression = update_expression.rstrip(', ')
    
    response = table.update_item(
        Key={
            'user_id': user_id,
            'blog_id': blog_id
        },
        UpdateExpression=update_expression,
        ExpressionAttributeValues=expression_attribute_values,
        ReturnValues='ALL_NEW'
    )
    return response.get('Attributes')

def delete_blog(user_id, blog_id):
    table.delete_item(
        Key={
            'user_id': user_id,
            'blog_id': blog_id
        }
    )

def lambda_handler(event, context):
    # Get user_id from Cognito authorizer
    logger.info("blog management triggered")
    logger.info(f"Event is {json.dumps(event)}")

    user_id = event['requestContext']['authorizer']['claims']['sub']
    user_email = event['requestContext']['authorizer']['claims']['email']
    user_id = user_email
    
    method = event['httpMethod']
    
    # Common headers for CORS
    headers = {
        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token,fileName',
        'Access-Control-Allow-Origin': 'http://localhost:4200',
        'Access-Control-Allow-Methods': 'POST, GET, PUT, OPTIONS, DELETE',
        'Access-Control-Allow-Credentials': 'true'
    }
    
    try:
        if method == 'OPTIONS':
            return {
                'statusCode': 200,
                'headers': headers,
                'body': ''
            }
            
        if method == 'POST':
            body = json.loads(event['body'])
            result = create_blog(user_id, body)
            return {
                'statusCode': 201,
                'headers': headers,
                'body': json.dumps(result)
            }
            
        elif method == 'GET':
            # Check if blog_id is provided
            path_parameters = event.get('pathParameters')
            if path_parameters and 'blog_id' in path_parameters:
                result = get_blog(user_id, path_parameters['blog_id'])
                if not result:
                    return {
                        'statusCode': 404,
                        'headers': headers,
                        'body': json.dumps({'error': 'Blog not found'})
                    }
            else:
                result = get_user_blogs(user_id)
                
            return {
                'statusCode': 200,
                'headers': headers,
                'body': json.dumps(result, default=decimal_default)
            }
            
        elif method == 'PUT':
            body = json.loads(event['body'])
            blog_id = event['pathParameters']['blog_id']
            result = update_blog(user_id, blog_id, body)
            
            if not result:
                return {
                    'statusCode': 404,
                    'headers': headers,
                    'body': json.dumps({'error': 'Blog not found'})
                }
                
            return {
                'statusCode': 200,
                'headers': headers,
                'body': json.dumps(result, default=decimal_default)
            }
            
        elif method == 'DELETE':
            blog_id = event['pathParameters']['blog_id']
            delete_blog(user_id, blog_id)
            return {
                'statusCode': 204,
                'headers': headers,
                'body': 'item deleted from table'
            }
            
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({'error': 'Internal server error'})
        }
