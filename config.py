import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', 'default_secret')
    # MySQL RDS 연결 문자열 예시: 'mysql+pymysql://username:password@host:3306/dbname'
    SQLALCHEMY_DATABASE_URI = os.environ.get('MYSQL_URI', 'mysql+pymysql://user:password@host:3306/dbname')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
    AWS_REGION = os.environ.get('AWS_REGION', 'ap-northeast-2')
    S3_BUCKET = os.environ.get('S3_BUCKET')
    DYNAMODB_TABLE = os.environ.get('DYNAMODB_TABLE', 'chat_data')
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
    TAGO_API_KEY = os.environ.get('TAGO_API_KEY')
    API_KEY = os.environ.get('API_KEY') 