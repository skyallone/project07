import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', 'default_secret')
    SQLALCHEMY_DATABASE_URI = os.environ.get('MYSQL_URI')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
    AWS_REGION = os.environ.get('AWS_REGION', 'ap-northeast-2')
    S3_BUCKET = os.environ.get('S3_BUCKET')
    DYNAMODB_TABLE = os.environ.get('DYNAMODB_TABLE', 'chat_data') 