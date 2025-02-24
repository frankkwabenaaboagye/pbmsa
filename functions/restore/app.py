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
    logger.info("deleting image started...")
    logger.info(f"Event: {event}")

    try:
        # Get user information from Cognito authorizer
        user_id = event['requestContext']['authorizer']['claims']['sub']
        user_email = event['requestContext']['authorizer']['claims']['email']
        user_id = user_email # changing this

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
        logger.info("Getting single image")
        user_images_table = dynamodb.Table(os.environ['USER_IMAGES_TABLE'])    
        user_images_table_response = user_images_table.get_item(
            Key={
                'user_id': user_id,
                'image_id': image_id
            }
        )
        logger.info(f"Response from DynamoDB: {user_images_table_response}")

        if 'Item' not in user_images_table_response:
            return {
                'statusCode': 404,
                'headers': myHeaders,
                'body': json.dumps({'error': 'Image not found'})
            }

        user_images_table_response_item = user_images_table_response['Item']

        deletion_type =  user_images_table_response_item['deletion_mode']

        if deletion_type != 'soft':
            return {
                'statusCode': 400,
                'headers': myHeaders,
                'body': json.dumps({'error': f'Cannot restore image with deletion type of {deletion_type}'})
            }

        logger.info('changing the deletion type to none')

        user_images_table_response_item['deletion_mode'] = 'none'

        # update the user images table
        logger.info("updating the table")
        user_images_table.put_item(Item=user_images_table_response_item)

        # update the user images sharing table too
        image_sharing_table = dynamodb.Table(os.environ['IMAGE_SHARING_TABLE'])
        image_sharing_table_response = image_sharing_table.scan()
        logger.info(f"Response from DynamoDB: {image_sharing_table_response}")

        try:
            image_sharing_table_items = image_sharing_table_response.get('Items', [])
        except Exception as e:
            logger.error(f"Error getting the items {str(e)}")
            image_sharing_table_items = []

        if len(image_sharing_table_items) != 0:
            for item in image_sharing_table_items:
                if item['image_id'] == image_id:
                    logger.info(f"Updating item in image_sharing_table: {item}")
                    image_sharing_table.update_item(
                        Key={
                            'share_token': item['share_token']
                        },
                        UpdateExpression='SET deletion_mode = :val',
                        ExpressionAttributeValues={
                            ':val': 'none'
                        }
                    )
                        
        return {
            'statusCode': 200,
            'headers': myHeaders,
            'body': json.dumps({
                'message': f'Successfully restored image - {image_id}'
            })
        }
    
    except Exception as e:
        print(f"Error processing upload: {str(e)}")
        return {
            'statusCode': 500,
            'headers': myHeaders,
            'body': json.dumps({
                'error': f"Error restoring image: {str(e)}"
            })
        }
        

