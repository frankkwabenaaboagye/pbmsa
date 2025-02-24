import json
import boto3
import base64
import uuid
import os
from datetime import datetime
import logging

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

logger = logging.getLogger()
logger.setLevel(logging.INFO)


myHeaders = {
    'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token,fileName',
    'Access-Control-Allow-Origin': 'https://main.d17gnlmjpnk7at.amplifyapp.com',
    'Access-Control-Allow-Methods': 'POST, GET, PUT, OPTIONS, DELETE',
    'Access-Control-Allow-Credentials': 'true'
}


def lambda_handler(event, context):
    logger.info("uploading images started...")
    # Maximum size in bytes (e.g., 6MB)
    MAX_SIZE = 6 * 1024 * 1024

    try:
        # Get user information from Cognito authorizer
        user_id = event['requestContext']['authorizer']['claims']['sub']
        user_email = event['requestContext']['authorizer']['claims']['email']
        user_id = user_email
        
        # Get the image data from the request
        if 'body' not in event or not event['body']:
            return {
                'statusCode': 400,
                'headers' : myHeaders,
                'body': json.dumps({'error': 'No image data provided'})
            }
        
        file_content = event['body']
        logger.info(f"file content is : {file_content}")

        # 'content-type': 'image/jpeg', 'filename': 'waterBottle.jpg

        # Get content type and filename from headers
        headers = event.get('headers', {})
        logger.info(f"headers is : {headers}")

        content_type = headers.get('Content-Type') or headers.get('content-type')
        if content_type is None:
            return {
                'statusCode': 400,
                'headers' : myHeaders,
                'body': json.dumps({'error': 'Content-Type not provided'})
            }
        logger.info(f"Content-Type is : {content_type}")

        file_name = headers.get('filename') or headers.get('fileName')
        if file_name is None:
            return {
                'statusCode': 400,
                'headers' : myHeaders,
                'body': json.dumps({'error': 'Filename not provided'})
            }
        logger.info(f"file name is : {file_name}")
        
        # Validate content type
        if not content_type.startswith('image/'):
            return {
                'statusCode': 400,
                'headers' : myHeaders,
                'body': json.dumps({'error': 'File must be an image'})
            }
        
        if event.get('isBase64Encoded', False):
            logger.info("Image is base64 encoded...decoding")
            file_content = base64.b64decode(file_content)
            # logger.info(f"file content is (after decoding) : {file_content}")

                    # Check file size (6MB limit) # use a MAX_SIZE variable
            logger.info("Checking file size...")
            if len(file_content) > MAX_SIZE:  # 6MB in bytes
                return {
                    'statusCode': 400,
                    'headers': myHeaders,
                    'body': json.dumps({'error': 'File size exceeds 6MB limit'})
                }
            
            # Generate unique image ID
            image_id = str(uuid.uuid4())

            # Generate S3 key (folder structure: user_id/filename)
            custom_file_name  = image_id + "_" + file_name

            # using the user_email as the user id
            user_id = user_email
            s3_key = f"{user_id}/{custom_file_name}"

            new_image_id = custom_file_name.split('.')[0]  # [su8792xuI_flower] [.jpg]

            # Check if the prams constains the blog id
            if event and "queryStringParameters" in event and event["queryStringParameters"]:
                query_params = event["queryStringParameters"]
                logger.info(f"Query parameters: {query_params}")

                if "blog_space_id" in query_params:
                    blog_space_id = query_params["blog_space_id"]
                else:
                    blog_space_id = "no id"


            logger.info("Upload to staging bucket...")
            s3.put_object(
                Bucket=os.environ['STAGE_BUCKET'],
                Key=s3_key,
                Body=file_content,
                ContentType=content_type,
                Metadata={
                    'user_id': user_id, # this is the user email now
                    'uploadTime': datetime.now().isoformat(),
                    'image_id': new_image_id,
                    'originalName': file_name,
                    'blog_space_id': blog_space_id
                }
            )

            # Store metadata in DynamoDB
            logger.info("Store metadata in DynamoDB...")
            images_table = dynamodb.Table(os.environ['USER_TABLE'])
            images_table.put_item(
                Item={
                    'user_id': user_id,
                    'image_id': new_image_id,
                    'status': 'processing',
                    'contentType': content_type,
                    'uploadTime': datetime.now().isoformat(),
                    'originalName': file_name,
                    'filename': file_name,
                    'size': len(file_content),
                    # 'url': image_url,
                    's3Key': s3_key,
                    'likes': 0,
                    'blog_space_id': blog_space_id
                }
            )

        else:
            logger.info("was not base64 encoded ")
            return {
                'statusCode': 400,
                'headers': myHeaders,
                'body': json.dumps({'error': 'File must be base64 encoded'})
            }



        # Generate public URL for the image
        # region = os.environ.get('AWS_REGION', 'eu-west-1')  # Get region from environment or default
        # bucket_name = os.environ['STAGE_BUCKET']
        # image_url = f"https://{bucket_name}.s3.{region}.amazonaws.com/{s3_key}"




        return {
            'statusCode': 200,
            'headers': myHeaders,
            'body': json.dumps({
                'message': 'Method completed',
                'imageId': new_image_id
            })
        }
    
    except Exception as e:
        print(f"Error processing upload: {str(e)}")
        return {
            'statusCode': 500,
            'headers': myHeaders,
            'body': json.dumps({
                'error': f"Error processing upload: {str(e)}"
            })
        }
        

