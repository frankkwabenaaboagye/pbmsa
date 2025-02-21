import json
import os

# Initialize a variable to hold the health status in memory
HEALTH_STATUS = {"status": "on"}  # Default to "on"
myheaders = {
    'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,X-Api-Key,X-Amz-Security-Token,fileName',
    'Access-Control-Allow-Origin': 'http://localhost:4200',
    'Access-Control-Allow-Methods': 'POST, GET, PUT, OPTIONS, DELETE',
}

def lambda_handler(event, context):
    global HEALTH_STATUS

    method = event['httpMethod']
    region = os.environ['THE_AWS_REGION']

    try:
        if method == 'OPTIONS':
            return {
                'statusCode': 200,
                'body': ''
            }
        
        if method == 'POST':
            # Parse the request body
            body = json.loads(event['body'])
            if 'status' in body and body['status'] in ['on', 'off']:
                HEALTH_STATUS['status'] = body['status']
                return {
                    'statusCode': 201,
                    'headers': myheaders,
                    'body': json.dumps({'message': 'Health status updated', 'status': HEALTH_STATUS['status']})
                }
            else:
                return {
                    'statusCode': 400,
                    'headers': myheaders,
                    'body': json.dumps({'message': 'Invalid status value. Use "on" or "off".'})
                }
        
        elif method == 'GET':
            if HEALTH_STATUS['status'] == 'off':
                return {
                    'statusCode': 503,
                    'headers': myheaders,
                    'body': json.dumps({'message': f'Service Unavailable - {region}'})
                }
            else:
                return {
                    'statusCode': 200,
                    'headers': myheaders,
                    'body': json.dumps({
                        'region': region,
                        'health_status': HEALTH_STATUS['status']
                    })
                }

        else:
            return {
                'statusCode': 405,
                'headers': myheaders,
                'body': json.dumps({'message': 'Method not allowed'})
            }

    except Exception as e:
        return {
            'statusCode': 500,
            'headers': myheaders,
            'body': json.dumps({'message': f'Internal server error: {str(e)}'})
        }

