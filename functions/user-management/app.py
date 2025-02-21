import json
import boto3
import os
import logging
import uuid

sns = boto3.client('sns')
logger = logging.getLogger()
logger.setLevel(logging.INFO)
cognito = boto3.client('cognito-idp')
dynamodb = boto3.resource('dynamodb')

def make_sure_role_exists(user_pool_id, username):
    logger.info(f"making sure role exists for {username}")
        
    try:
        user_response = cognito.admin_get_user(
            UserPoolId=user_pool_id,
            Username=username
        )

        current_attributes = {attr['Name']: attr['Value'] for attr in user_response['UserAttributes']}
        logger.info(f"current attribute => {current_attributes}")

        # Check if all required attributes exist and custom:role is TeamMember
        if ('email' not in current_attributes or 'name' not in current_attributes):
            
            # Prepare attributes update maintaining email and name if they exist
            update_attributes = [
                {'Name': 'email', 'Value': current_attributes.get('email', username)},
                {'Name': 'name', 'Value': current_attributes.get('name', username)}
            ]
            
            logger.info(f"Updating user attributes for {username}")
            cognito.admin_update_user_attributes(
                UserPoolId=user_pool_id,
                Username=username,
                UserAttributes=update_attributes
            )
            print(f"Successfully updated attributes for user {username}")
    except Exception as e:
        logger.info(f"Error in make_sure_role_exists: {str(e)}")


def get_user_pool_ids():
    # Create SSM clients for both regions
    logger.info("getting user pool ids...")
    ssm_eu_west = boto3.client('ssm', region_name='eu-west-1')
    ssm_eu_central = boto3.client('ssm', region_name='eu-central-1')
    
    logger.info("getting stack name")
    stack_name = os.environ['STACK_NAME']
    
    try:
        # Get User Pool ID from eu-west-1
        eu_west_pool_id = ssm_eu_west.get_parameter(
            Name=f"/{stack_name}/eu-west-1/UserPoolId"
        )['Parameter']['Value']

        logger.info(f"eu_west_pool_id = {eu_west_pool_id}")
        
        # Get User Pool ID from eu-central-1
        eu_central_pool_id = ssm_eu_central.get_parameter(
            Name=f"/{stack_name}/eu-central-1/UserPoolId"
        )['Parameter']['Value']

        logger.info(f"eu_central_pool_id = {eu_central_pool_id}")
        
        return {
            'eu-west-1': eu_west_pool_id,
            'eu-central-1': eu_central_pool_id
        }
    except Exception as e:
        print(f"Error getting User Pool IDs: {str(e)}")
        raise


def get_user_by_email(email, user_pool_id):
    response = cognito.list_users(
        UserPoolId=user_pool_id,
        Filter=f'email = "{email}"'
    )
    return response


def lambda_handler(event, context):
    """
    Handles post confirmation of users:
    1. Adds user to PhotoBlogUserGroup
    """
    logger.info('post confirmation executing...')
    try:
        # Part 1: Add user to PhotoBlogUserGroup group
        user_pool_id = event['userPoolId']
        logger.info(f"user_pool_id is => {user_pool_id}")
        username = event['userName']
        logger.info(f"username is => {username}")

        #--------------to make sure role is set
        make_sure_role_exists(user_pool_id, username)

        
        # print("Starting part 1: Adding user to PhotoBlogUserGroup")
        logger.info("adding user to PhotoBlogUserGroup")
        cognito.admin_add_user_to_group(
            UserPoolId=user_pool_id,
            Username=username,
            GroupName='PhotoBlogUserGroup'
        )

    
        # print(f"Successfully added user {username} to PhotoBlogUserGroup")

        # Part 2: Start subscription workflow
        # print("Starting part 2: Initiating subscription workflow")
        user_email = event['request']['userAttributes']['email']
        


        # getting the user by email
        logger.info("tesing getting user by email")
        try:
            the_response_from_gube= get_user_by_email(user_email, user_pool_id) # the response from get user by email
            logger.info(f"the_response_from_gube = {the_response_from_gube}")
        except Exception as e:
            logger.info(f"error getting user by email {e}")

        
        # Subscribe user to the SNS topic
        logger.info(f"subscribing user... {os.environ['SNS_TOPIC_ARN']}")
        # login notification subscription

        login_response = sns.subscribe(
            TopicArn=os.environ['SNS_TOPIC_ARN'],
            Protocol='email',
            Endpoint=user_email,
            ReturnSubscriptionArn=True
        )
        # logger.info(f"Subscription created for user {username} with email {user_email}")
        # logger.info(f"Subscription response: {response}")
        # retry notification subscription
        logger.info(f"subscribing user...{os.environ['SNS_RETRY_TOPIC_ARN']}")
        processing_response = sns.subscribe(
            TopicArn=os.environ['SNS_RETRY_TOPIC_ARN'],
            Protocol='email',
            Endpoint=user_email,
            ReturnSubscriptionArn=True
        ) 
        # Filter by email since it's the endpoint
        filter_policy = {
            "email": [user_email]  # Filter by the email address
        }
        sns.set_subscription_attributes(
            SubscriptionArn=processing_response['SubscriptionArn'],
            AttributeName='FilterPolicy',
            AttributeValue=json.dumps(filter_policy)
        )
        
        # logger.info(f"Subscription created for user {username} with email {user_email}")
        # logger.info(f"Subscription response: {response}")

        # after we are done with everything, I am
        # checking the region we are in so that, I 
        # replicate the users in the other region
        current_region = os.environ['THE_AWS_REGION']
        logger.info(f"current region  = {current_region}")

        if current_region == 'eu-west-1':
            # then we replicate the user to the other region
            # logger.info("replicating user...(1/2)")

            secondary_region = 'eu-central-1'
            primary_region = current_region

            # Get both User Pool IDs
            user_pool_ids = get_user_pool_ids()
            logger.info(f"user_pool_ids = {user_pool_ids}")


            # Determine which is the secondary region
            secondary_pool_id = user_pool_ids[secondary_region]
            primary_pool_id = user_pool_ids[primary_region]

            # Create Cognito client for secondary region
            # cognito_secondary = boto3.client('cognito-idp', region_name=secondary_region)

            # logger.info("creating user in secondary region...")
            # Generate a secure temporary password
            # temp_password = f"photoblogR2!{uuid.uuid4().hex[:8]}"
            # logger.info(f"generated temp password is -> {temp_password}")

            # response_from_sac = cognito_secondary.admin_create_user(
            #     UserPoolId=secondary_pool_id,
            #     Username=user_email,
            #     UserAttributes=[
            #         {'Name': 'email', 'Value': user_email},
            #         {'Name': 'email_verified', 'Value': 'true'},
            #     ],
            #     MessageAction='SUPPRESS',
            #     TemporaryPassword=temp_password
            # )

            # logger.info(f"response from secondary region adding user = {response_from_sac}")

            # set permanent password
            # logger.info("setting permanent password in secondary region...")

                # a design consideration - not setting the permanent password
            # cognito_secondary.admin_set_user_password(
            #     UserPoolId=secondary_pool_id,
            #     Username=user_email,
            #     Password=temp_password,
            #     Permanent=True
            # )
            # logger.info("setting permanent password in secondary region...(2/2)")

            # logger.info("add user to group in secondary region...(2/2)")

            # then we add the user to the group in the other region
            # cognito_secondary.admin_add_user_to_group(
            #     UserPoolId=secondary_pool_id,
            #     Username=user_email,
            #     GroupName='PhotoBlogUserGroup'
            # )
            # logger.info(f"Successfully replicated user {username} to {user_pool_ids['eu-central-1']}")

            # store user information in the global user information dynamo db table
            # logger.info("storing user information in the global user information dynamo db table...(1/2)")
        
            table_name = os.environ['GLOBAL_USER_INFO_TABLE_NAME']

            table = dynamodb.Table(table_name)
     
            item = {
                'user_id': user_email, # making the user_id same as the user_eamil
                'old_user_name': username,
                'primary_user_pool_id': primary_pool_id,
                'secondary_user_pool_id': secondary_pool_id,
                'primary_region': primary_region,
                'secondary_region': secondary_region,
                'status': 'ACTIVE_IN_REGION_1', # another option will be ACTIVE_IN_REGION_2
            }
            table.put_item(Item=item)
            logger.info(f"Successfully stored user {user_email} information in the global user information dynamo db table")

            logger.info("user added successfully...")

        elif current_region == 'eu-central-1':
            logger.info("simulating sending out an email to the user.. since, its a DR")
        
        return event
        
    except Exception as e:
        print(f"Error in post confirmation handler: {str(e)}")
        raise e

