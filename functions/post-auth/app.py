import json
import boto3
import os
import logging
from datetime import datetime

sns = boto3.client('sns')
logger = logging.getLogger()
logger.setLevel(logging.INFO)
cognito = boto3.client('cognito-idp')



def get_message(user_name, login_time):
    return f"""
    Hello {user_name},
    
    This is to notify you that your account was accessed at {login_time}.
    If this wasn't you, please contact support immediately.
    Yes Immediately.
    
    Best regards,
    Your Application Team - Photo App - Frank
    """

def lambda_handler(event, context):

    try:
        logger.info("handling post auth...")

        logger.info(f"the event: {event}")

        user_attribute = event['request']['userAttributes']
        email = user_attribute['email']
        # user_name = user_attribute.get('userName', email)
        username = event['userName']

        # get the current time
        login_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        message = get_message(username, login_time)

        # send the notification
        sns.publish(
            TopicArn=os.environ['SNS_TOPIC_ARN'],
            Message=message,
            Subject='New Login Detected',
            MessageAttributes={
                'email': {
                    'DataType': 'String',
                    'StringValue': email
                }
            }
        )
        logger.info(f"Login notification sent for user: {username}")

    except Exception as e:
        logger.error(f"Error in post authentication handler: {str(e)}")
        pass
    
    return event