import json
import boto3
import base64
import uuid
import os
from datetime import datetime
import logging
from boto3.dynamodb.conditions import Key

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
    logger.info("deleting image started...")

    try:
        # Get user information from Cognito authorizer
        user_id = event['requestContext']['authorizer']['claims']['sub']
        user_email = event['requestContext']['authorizer']['claims']['email']

        user_id = user_email # we are changing the user id to be the user email

        image_id = None

         # Check if this is a shared image access
        if event and "pathParameters" in event and event["pathParameters"]:
            path_params = event["pathParameters"]
            logger.info(f"Path parameters: {path_params}")

            if "image_id" in path_params:
                image_id = path_params["image_id"]
  
        if image_id is None:
            return {
                'statusCode': 400,
                'headers': myHeaders,
                'body': json.dumps({'error': 'Invalid image ID'})
            }

        deletion_type = None
        
        if event and "queryStringParameters" in event and event["queryStringParameters"]:
            query_params = event["queryStringParameters"]
            logger.info(f"Query parameters: {query_params}")

            if "deletion_type" in query_params:
                deletion_type = query_params["deletion_type"]

        if deletion_type not in ["soft", "hard"] or deletion_type is None:
            return {
                'statusCode': 400,
                'headers': myHeaders,
                'body': json.dumps({'error': 'Invalid deletion_type parameter'})
            }
            
        logger.info(f"Deletion type: {deletion_type}")

        logger.info("Getting single image")

        user_images_table = dynamodb.Table(os.environ['USER_IMAGES_TABLE'])
        image_sharing_table = dynamodb.Table(os.environ['IMAGE_SHARING_TABLE'])
        processed_images_s3_bucket = os.environ['PROCESSED_BUCKET']
    
        user_images_table_response = user_images_table.get_item(
            Key={
                'user_id': user_id,
                'image_id': image_id
            }
        )

        logger.info(f"Response from user_images DynamoDB: {user_images_table_response}")

        if 'Item' not in user_images_table_response:
            return {
                'statusCode': 404,
                'headers': myHeaders,
                'body': json.dumps({'error': 'Image not found'})
            }

        user_images_table_item = user_images_table_response['Item']

        image_sharing_table_response = image_sharing_table.scan()
        logger.info(f"Response from DynamoDB: {image_sharing_table_response}")

        # search in the image_sharing_table and delete object accordingly
        try:
            image_sharing_table_items = image_sharing_table_response.get('Items', [])
        except Exception as e:
            logger.error(f"Error getting the items {str(e)}")
            image_sharing_table_items = []

        if deletion_type == 'soft':
            logger.info("it is a soft deletion...")
            user_images_table_item['deletion_mode'] = 'soft'
            logger.info("Updating item in the table...")
            user_images_table.put_item(Item=user_images_table_item)


        elif deletion_type == 'hard':
            logger.info("it is a hard deletion...")

            # delete from table
            logger.info("deleting from table...")
            user_images_table.delete_item(
                Key={
                    'user_id': user_id,
                    'image_id': image_id
                }
            )

            theKey = user_images_table_item['s3Key']
            logger.info(f"the s3 bucket Key => {theKey}")

            # delete from s3
            logger.info("deleting from s3...")
            s3.delete_object(
                Bucket=processed_images_s3_bucket,
                Key=theKey
            )

        # delete from image_sharing_table
        if len(image_sharing_table_items) != 0:
            for item in image_sharing_table_items:
                if item['image_id'] == image_id:
                    if deletion_type == 'soft': 
                        logger.info(f"Updating item in image_sharing_table: {item}")
                        image_sharing_table.update_item(
                            Key={
                                'share_token': item['share_token']
                            },
                            UpdateExpression='SET deletion_mode = :val',
                            ExpressionAttributeValues={
                                ':val': 'soft'
                            }
                        )
                    elif deletion_type == 'hard':
                        logger.info(f"Deleting item from image_sharing_table: {item}")
                        image_sharing_table.delete_item(
                            Key={
                                'share_token': item['share_token']
                            }
                        )
                        logger.info(f"Deleted item from image_sharing_table: {item}")
        
        return {
            'statusCode': 200,
            'headers': myHeaders,
            'body': json.dumps({
                'message': f'Successfully deleted {image_id} - using {deletion_type} deletion'
            })
        }
    
    except Exception as e:
        print(f"Error processing upload: {str(e)}")
        return {
            'statusCode': 500,
            'headers': myHeaders,
            'body': json.dumps({
                'error': f"Error deleting image: {str(e)}"
            })
        }
        

