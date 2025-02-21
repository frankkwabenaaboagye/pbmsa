import json
import boto3
import base64
import uuid
import os
from datetime import datetime, timedelta
import logging
from boto3.dynamodb.conditions import Key
import decimal


s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SHARE_LINK_EXPIRATION = 10800  # 3 hours in seconds
EXPIRATION_FOR_AUTH_USERS = 60  * 60 * 24 # 24 hours in seconds

domain_name = "main.d17gnlmjpnk7at.amplifyapp.com"
stage = "prod"

myHeaders = {
    'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token,fileName',
    'Access-Control-Allow-Origin': 'http://localhost:4200',
    'Access-Control-Allow-Methods': 'POST, GET, PUT, OPTIONS, DELETE',
    'Access-Control-Allow-Credentials': 'true'
}


def handle_shared_image_access(share_token):
    # Get sharing record from DynamoDB
    logger.info("handle_shared_image_access invoked")
    sharing_table = dynamodb.Table(os.environ['IMAGE_SHARING_TABLE'])
    response = sharing_table.get_item(
        Key={
            'share_token': share_token
        }
    )
    logger.info(f"response: {response}")

    if 'Item' not in response:
        return {
            'statusCode': 404,
            'headers': myHeaders,
            'body': json.dumps({'error': 'Shared link not found or has expired'})
        }
    
    share_record = response['Item']

    # Generate presigned URL with remaining time as expiration
    # remaining_time = int(share_record['expires_at'] - datetime.now().timestamp())
    # presigned_url = s3.generate_presigned_url(
    #     'get_object',
    #     Params={
    #         'Bucket': os.environ['PROCESSED_BUCKET'],
    #         'Key': f"{share_record['user_id']}/{share_record['image_id']}"
    #     },
    #     ExpiresIn=remaining_time
    # )

    return {
        'statusCode': 200,
        'headers': myHeaders,
        'body': json.dumps({
            'data': share_record
        }, default=decimal_default)
    }


def generate_share_link(user_id, image_id, metadata, presigned_url_guest):
    logger.info(f"Generating share link for user {user_id} and image {image_id} ")
    share_token = str(uuid.uuid4())
    expiration_time = datetime.now() + timedelta(seconds=SHARE_LINK_EXPIRATION)
    # Store sharing information in DynamoDB
    sharing_table = dynamodb.Table(os.environ['IMAGE_SHARING_TABLE'])
    share_item = {
        'share_token': share_token,
        'user_id': user_id,
        'image_id': image_id,
        'created_at': datetime.now().isoformat(),
        'expires_at': int(expiration_time.timestamp()),  # TTL attribute for DynamoDB
        'presigned_url_guest': presigned_url_guest,
        'deletion_mode': 'none',
        'metadata': {
            'shared_by': user_id,
            'shared_at': datetime.now().isoformat(),
            'expires_at': expiration_time.isoformat(),
            **metadata
        }
    }
    sharing_table.put_item(Item=share_item)

    # Generate the sharing URL
    share_url = f"https://{domain_name}/guest-view/shared/{share_token}"
    
    

    return {
        'shareUrl': share_url,
        'expiresAt': expiration_time.isoformat(),
        'shareToken': share_token
    }


def get_single_image(user_id, image_id, table, generate_share=False):
    # Get specific image
    logger.info("Getting single image")

    
    response = table.get_item(
        Key={
            'user_id': user_id,
            'image_id': image_id
        }
    )

    logger.info(f"Response from DynamoDB: {response}")

    if 'Item' not in response:
        return {
            'statusCode': 404,
            'headers': myHeaders,
            'body': json.dumps({'error': 'Image not found'})
        }

    item = response['Item']

    # Generate presigned URL for authenticated user
    s3_key = item.get('s3Key')
    logger.info(f"s3_key => {s3_key}")

    presigned_url = s3.generate_presigned_url(
        'get_object',
        Params={
            'Bucket': os.environ['PROCESSED_BUCKET'],
            'Key': s3_key
        },
        ExpiresIn=EXPIRATION_FOR_AUTH_USERS  # URL valid for 1 hour for authenticated users
    )

    # for guests
    presigned_url_guest = s3.generate_presigned_url(
        'get_object',
        Params={
            'Bucket': os.environ['PROCESSED_BUCKET'],
            'Key': s3_key
        },
        ExpiresIn=SHARE_LINK_EXPIRATION  # URL valid for 1 hour for authenticated users
    )

    item['presignedUrl'] = presigned_url

    # Generate sharing link if requested
    if generate_share:
        share_info = generate_share_link(user_id, image_id, item.get('metadata', {}), presigned_url_guest)
        logger.info(f"share_info => {share_info}")
        item['shareInfo'] = share_info

    return {
        'statusCode': 200,
        'headers': myHeaders,
        'body': json.dumps({
            'image': item
        }, default=decimal_default)
    }

def decimal_default(obj):
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    raise TypeError("Type not serializable")


def get_all_user_images(user_id, table):
    # List all user's processed images
    logger.info(f"Getting all images for user {user_id}")
    response = table.query(
        KeyConditionExpression=Key('user_id').eq(user_id),
        FilterExpression='attribute_exists(#url_attr)',
        ExpressionAttributeNames={
            '#url_attr': 'url'
        }
    )
    logger.info(f"Response from DynamoDB: {response}")

    items = response.get('Items', [])
    # Generate presigned URLs for each image
    logger.info("Generating presigned URLs for each image")
    for item in items:

        logger.info(f"item => {item}")

        s3_key = item['s3Key']
        logger.info(f"s3_key => {s3_key}")

        try:
            # Check if the object exists first
            s3.head_object(
                Bucket=os.environ['PROCESSED_BUCKET'],
                Key= s3_key
            )

            presigned_url = s3.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': os.environ['PROCESSED_BUCKET'],
                    'Key': s3_key
                },
                ExpiresIn=EXPIRATION_FOR_AUTH_USERS
            )
            item['presignedUrl'] = presigned_url
            logger.info(f"presignedUrl => {presigned_url}" )
            # update
            table.put_item(Item=item)
        except Exception as e:
            logger.error(f"Error generating presigned URL: {str(e)}")
            item['presignedUrl'] = None
            item['status'] = 'image_not_found'

    return {
        'statusCode': 200,
        'headers': myHeaders,
        'body': json.dumps({
            'images': items,
            'count': len(items)
        }, default=decimal_default)
    }




def lambda_handler(event, context):

    global domain_name, stage

    logger.info("ViewImageFunction has been invoked..")
    logger.info(f"Event is {json.dumps(event)}")

    try:

        # Check if this is a shared image access
        if event and "pathParameters" in event and event["pathParameters"]:
            path_params = event["pathParameters"]
            logger.info(f"Path parameters: {path_params}")

            if "share_token" in path_params:
                logger.info("Shared image access detected")
                return handle_shared_image_access(path_params["share_token"])

            if "image_id" in path_params:
                image_id = path_params["image_id"]
            else:
                image_id = None
        else:
            image_id = None

        # Check if this is a request to generate a share link
        if event and "queryStringParameters" in event and event["queryStringParameters"]:
            query_params = event["queryStringParameters"]
            logger.info(f"Query parameters: {query_params}")

            generate_share = "generate_share" in query_params and query_params["generate_share"] == "true"
        else:
            generate_share = False

        logger.info(f"Image ID: {image_id}")
        
        user_id = event['requestContext']['authorizer']['claims']['sub']
    
        user_email = event['requestContext']['authorizer']['claims']['email']
        user_id = user_email # we are changing the user id  to the user email

        table = dynamodb.Table(os.environ['USER_IMAGES_TABLE'])

        if image_id:
            # domain_name = event['requestContext']['domainName']
            stage = event['requestContext']['stage']
            logger.info(f"Domain name: {domain_name}, Stage: {stage}")
            return get_single_image(user_id, image_id, table, generate_share)
        else:
            
            return get_all_user_images(user_id, table)
        
    except Exception as e:
        logger.info(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': myHeaders,
            'body': json.dumps({'error': str(e)})
        }
