import json
import boto3
import io
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
import os
import logging
import requests
import urllib.parse

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
sns = boto3.client('sns')
cognito = boto3.client('cognito-idp')
sqs = boto3.client('sqs')

logger = logging.getLogger()
logger.setLevel(logging.INFO)

myHeaders = {
    'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token,fileName',
    'Access-Control-Allow-Origin': 'https://main.d17gnlmjpnk7at.amplifyapp.com',
    'Access-Control-Allow-Methods': 'POST, GET, PUT, OPTIONS, DELETE',
    'Access-Control-Allow-Credentials': 'true'
}


FONT_PATH = "/tmp/arialbd.ttf" 
FONT_URL = "https://github.com/matomo-org/travis-scripts/raw/master/fonts/Arial_Bold.ttf"  # Publicly available Arial Bold font

PHOTOAPPUSER = "user"
attempt = 1

def ensure_font_exists():
    if not os.path.exists(FONT_PATH):
        logger.info("Downloading Arial Bold font...")
        response = requests.get(FONT_URL)
        if response.status_code == 200:
            with open(FONT_PATH, "wb") as font_file:
                font_file.write(response.content)
            logger.info("Font downloaded successfully!")
        else:
            logger.info("Failed to download font, using default.")

def add_watermark(image_bytes, user_name, include_strokes=False):
    # global PHOTOAPPUSER
    # PHOTOAPPUSER = user_name

    # print(PHOTOAPPUSER)

    logger.info("Adding watermark to image...")
    # Open the image
    input_image = Image.open(io.BytesIO(image_bytes))
    original_format = input_image.format or "PNG"  # Default to PNG if format is missing
    input_image = input_image.convert('RGBA')
    width, height = input_image.size

    overlay = Image.new('RGBA', input_image.size, color=(0, 0, 0, 0))  # Fully transparent overlay
    draw = ImageDraw.Draw(overlay)

    # Deep bold watermark color pattern (more opacity)
    watermark_color_pattern = (255, 255, 255, 255)  # White with stronger opacity

    # Draw diagonal watermark lines
    if include_strokes:
        for i in range(0, width + height, 50):
            draw.line([(0, height - i), (i, height)], fill=watermark_color_pattern, width=8)  # Thicker lines
    
    # Load font with bold effect
    font_size = max(90, width // 15)

    ensure_font_exists() # comment out when testing

    try:
        font = ImageFont.truetype(FONT_PATH, font_size)  # 'arialbd.ttf' is the bold version
        logger.info("font arialbd is being used")
        print("yes")
    
    except IOError:
        font = ImageFont.load_default()  # Fallback if Arial Bold is not found
        logger.info("default is being used")
        font_size = 120
        print("no")

    # Add watermark text
    watermark_text = f"{PHOTOAPPUSER}\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
    # Calculate text size with spacing
    padding = 30  # Extra spacing around text
    try:
        bbox = draw.textbbox((0, 0), watermark_text, font=font)
        text_width = bbox[2] - bbox[0] + padding
        text_height = bbox[3] - bbox[1] + padding
    except AttributeError:  # Fallback for older Pillow versions
        text_width = text_height = 300

    # Position watermark text in the center with extra spacing
    x = (width - text_width) // 2
    y = (height - text_height) // 2

    # Strong bold text color (more contrast)
    watermark_color_text = (255, 255, 255, 230)  # White with higher opacity

    # Draw text multiple times to make it bolder (shadow effect)
    offsets = [-3, 0, 3]
    # for offset in offsets:
    #     draw.text((x + offset, y), watermark_text, fill=watermark_color_text, font=font)
    stroke_width = 3 
    stroke_color = (0, 0, 0, 255)
    draw.text((x, y), watermark_text, fill=watermark_color_text, font=font, stroke_fill=stroke_color, stroke_width=stroke_width)

    # Merge the overlay with the original image
    watermark_image = Image.alpha_composite(input_image, overlay)

    watermark_image = watermark_image.convert("RGB")

    # Save the watermarked image
    output = io.BytesIO()
    watermark_image.save(output, format=original_format)
    # seek
    output.seek(0)

    return output.getvalue()


def unquote(anyString):
    return urllib.parse.unquote(anyString)


def get_user_by_email(email, user_pool_id):
    decoded_email = urllib.parse.unquote(email)
    logger.info(f"decoded email => {decoded_email}")
    response = cognito.list_users(
        UserPoolId=user_pool_id,
        Filter=f'email = "{decoded_email}"'
    )
    return response


def get_user_details(user_id):
    # the user id coming in here is the email
    logger.info("getting user details... ")
    response = get_user_by_email(user_id, os.environ['USER_POOL_ID'])
    logger.info(f"the response from gube => {response}")

    # we want the sub here
    username = response['Users'][0]['Username'] if 'Users' in response and response['Users'] else None
    logger.info(f"The username: {username}")

    try:
        response = cognito.admin_get_user(
            UserPoolId=os.environ['USER_POOL_ID'],
            Username=username
        )
        
        # Extract first name and last name from user attributes
        user_attrs = {attr['Name']: attr['Value'] for attr in response['UserAttributes']}
        logger.info(f"The User attributes: {user_attrs}")

        user_name = user_attrs.get('name', user_attrs.get('email', 'dummyUsername'))

        return {
            'user_name': user_name,
            'email': user_attrs.get('email', 'dummyEmail@gmail.com')
        }
    except Exception as e:
        logger.error(f"Error getting user details: {str(e)}")
        return {'user_name': 'exceptionUsername', 'email': 'no-email-provided'}
    
def lambda_handler(event, context):
    logger.info("processing images invoked...")

    global attempt
    attempt = 1

    logger.info(f"Event coming in  => {json.dumps(event)}")

    try:

        

        # Check if this is an SQS retry
        if 'Records' in event and event['Records'][0].get('eventSource') == 'aws:sqs':
            logger.info("This is an SQS retry...")
            message = json.loads(event['Records'][0]['body'])
            attempt = message.get('attempt', 1)
            logger.info(f"for Retry: attemp is => {attempt}")
            bucket = message.get('bucket')
            key = message.get('key')
            logger.info(f"key gotten => {key}")
        else:
            # Initial S3 trigger
            logger.info("This is an initial S3 trigger...")
            key = event['Records'][0]['s3']['object']['key']
            bucket = event['Records'][0]['s3']['bucket']['name']
            logger.info(f"bucket is : {bucket}")

        key = unquote(key)
        logger.info(f"key unquoted => {key}")
        logger.info(f"Processing key: {key}, attempt: {attempt}")

        # Extract user_id and get user details
        user_id = key.split('/')[0] # this is the email
    
        user_details = get_user_details(user_id)
        user_name = user_details['user_name']
        email = user_details['email']

        # write a check here for the username

        global PHOTOAPPUSER
        PHOTOAPPUSER = user_name
        
        # Get the image from the staging 
        logger.info(f"Getting image from bucket: {bucket}")
        response = s3.get_object(Bucket=bucket, Key=key)
        logger.info(f"response is : {response}")
        image_content = response['Body'].read()

        # # Get user information from the key (assuming key format: userid/imageid_<fileName.ext>) // image id is the file name here
        image_id = key.split('/')[1].split('.')[0]

        # try to simulate a fail, if the image name is starts with black
        if 'black' in image_id:
            raise Exception("Simulated failure..")

        # Add watermark
        processed_image = add_watermark(image_content, user_name, False)  # Get actual user name from Cognito

        # # Upload to primary bucket
        primary_bucket = os.environ['PRIMARY_BUCKET']
        logger.info("Uploading to primary bucket...")
        s3.put_object(
            Bucket=primary_bucket,
            Key=key,
            Body=processed_image,
            ContentType=response['ContentType']
        )

        # # Update DynamoDB
        logger.info("Store metadata in DynamoDB...")
        table = dynamodb.Table(os.environ['USER_TABLE'])

        logger.info("Getting metadata..")
        if 'Metadata' in response:
            metadata = response['Metadata']
            logger.info(f"Metadata: {metadata}")
        else: 
            metadata = {}

        try:
            the_region = os.environ['THE_REGION']
        except Exception as e:
            the_region = 'eu-west-1'
            

        table.put_item(
            Item={
                'user_id': user_id,
                'image_id': image_id,
                'status': 'water-marked',
                'url': f"https://{primary_bucket}.s3.{the_region}.amazonaws.com/{key}",
                'createdAt': datetime.now().isoformat(),
                'uploadTime': datetime.now().isoformat(),
                'contentType': response['ContentType'],
                'size': len(processed_image),
                'attempts': attempt,
                's3Key': key,
                'likes': 0,
                'deletion_mode': 'none', # can be none, soft, hard
                'metadata': {
                    **metadata
                }
            }
        )

        # deletion mode can be none, soft, hard

        # Delete from staging bucket
        logger.info("Deleting object from staging")
        s3.delete_object(Bucket=bucket, Key=key)
        
        logger.info("Image processed and uploaded successfully")

        return {
            'statusCode': 200,
            'headers': myHeaders,
            'body': json.dumps({'message': 'Image processed and uploaded successfully'})
        }

    except Exception as e:
        logger.error(f"Error processing image: {str(e)}")

        if attempt < 3:
            # send to sqs for retry
            logger.info("sending to sqs for retry")
            sqs.send_message(
                QueueUrl=os.environ['SQS_QUEUE_URL'],
                MessageBody=json.dumps({
                    'bucket': bucket,
                    'key': key,
                    'attempt': attempt + 1,
                    'error': str(e)
                }),
                DelaySeconds=60  # 1 minute delay #DelaySeconds=300  # 5 minute delay
            )
        
            # Send failure notification
            logger.info("sending failure notification")
            logger.info("Attempt is = " + event.get('attempt', "No atempt in the event"))
            sns.publish(
                TopicArn=os.environ['SNS_RETRY_TOPIC_ARN'],
                Message=f"""
                Hello {PHOTOAPPUSER},
                
                We encountered an issue processing your image: {key}
                Attempt: {attempt} of 3
                
                Don't worry - we'll automatically retry the processing in 5 minutes.
                You'll receive another notification about the status.
                
                Best regards,
                Your App Team - Photo Blog - Frank
                """,
                Subject='Image Processing Failed - Automatic Retry Scheduled',
                MessageAttributes={
                    'email': {
                        'DataType': 'String',
                        'StringValue': email
                    }
                }
            )

        else:
            # Final failure notification
            sns.publish(
                TopicArn=os.environ['SNS_RETRY_TOPIC_ARN'],
                Message=f"""
                Hello {PHOTOAPPUSER},
                
                We're sorry, but we were unable to process your image: {key}
                after {attempt} attempts.
                
                Please try uploading the image again or contact support if the issue persists.
                
                Best regards,
                Your App Team - Photo Blog - Frank
                """,
                Subject='Image Processing Failed - Maximum Retries Reached',
                MessageAttributes={
                    'email': {
                        'DataType': 'String',
                        'StringValue': email
                    }
                }
            )
        
        return {
            'statusCode': 500,
            'headers': myHeaders,
            'body': json.dumps({'Error processing image': str(e)})
        }



# Send success notification if this was a retry
        # if attempt > 1:
        #     sns.publish(
        #         TopicArn=os.environ['SNS_TOPIC_ARN'],
        #         Message=f"""
        #         Hello,
                
        #         Good news! Your image has been successfully processed after {attempt} attempts.
        #         You can view it at: https://{primary_bucket}.s3.amazonaws.com/{key}
                
        #         Best regards,
        #         Your App Team - Photo Blog
        #         """,
        #         Subject='Image Processing Succeeded',
        #         MessageAttributes={
        #             "email": {
        #                 "DataType": "String",
        #                 "StringValue": email
        #             }
        #         }
        #     )