from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import os
import json
import time
import google.generativeai as genai
import boto3
from config import Config
from boto3.dynamodb.conditions import Key
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = Config.SECRET_KEY
app.config['SQLALCHEMY_DATABASE_URI'] = Config.SQLALCHEMY_DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    password_hash = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Favorite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    departure = db.Column(db.String(100), nullable=False)
    arrival = db.Column(db.String(100), nullable=False)
    transport_type = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('favorites', lazy=True))

# DynamoDB 연결 (AI 대화)
dynamodb = boto3.resource(
    'dynamodb',
    region_name=Config.AWS_REGION,
    aws_access_key_id=Config.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=Config.AWS_SECRET_ACCESS_KEY
)
chat_table = dynamodb.Table(Config.DYNAMODB_TABLE)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# S3 이미지 URL 생성 함수도 고정값 사용
import urllib.parse
def get_s3_image_url(filename):
    return f"https://project-trip-pic.s3.ap-northeast-2.amazonaws.com/{urllib.parse.quote(filename)}"

@app.context_processor
def inject_global_vars():
    return dict(get_s3_image_url=get_s3_image_url)

# 회원가입 라우트
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            flash('이미 존재하는 사용자명입니다.', 'error')
            return redirect(url_for('register'))
        if User.query.filter_by(email=email).first():
            flash('이미 존재하는 이메일입니다.', 'error')
            return redirect(url_for('register'))
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash('회원가입이 완료되었습니다. 로그인 해주세요.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

# 로그인 라우트
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            flash('로그인 성공!', 'success')
            return redirect(url_for('index'))
        else:
            flash('아이디 또는 비밀번호가 올바르지 않습니다.', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('로그아웃되었습니다.', 'info')
    return redirect(url_for('index'))

@app.route('/chatbot')
def chatbot():
    return render_template('chatbot.html')

@app.route('/mypage')
@login_required
def mypage():
    # 예매내역 대신 AI 대화내역을 가져옴
    chat_history = chat_table.query(
        KeyConditionExpression=Key('user_id').eq(str(current_user.id)),
        ScanIndexForward=False,
        Limit=50
    )['Items']
    favorites = list(Favorite.query.filter_by(user_id=current_user.id).all())

    def safe_str(val):
        if val is None:
            return ''
        try:
            return str(val)
        except Exception:
            return ''

    chat_history_dicts = [
        {
            'id': safe_str(chat['timestamp']),
            'message': safe_str(chat['message']),
            'response': safe_str(chat['response']),
            'timestamp': datetime.fromtimestamp(float(chat['timestamp'])).strftime('%Y-%m-%d %H:%M')
        }
        for chat in chat_history
    ]
    favorites_dicts = [
        {
            'id': safe_str(fav.id),
            'departure': safe_str(fav.departure),
            'arrival': safe_str(fav.arrival),
            'transport_type': safe_str(fav.transport_type),
            'created_at': datetime.fromtimestamp(fav.created_at.timestamp()).strftime('%Y-%m-%d') if fav.created_at else ''
        }
        for fav in favorites
    ]

    return render_template('mypage.html', chat_history=chat_history_dicts, favorites=favorites_dicts)

@app.route('/search_transportation', methods=['POST'])
def search_transportation():
    departure = request.form.get('departure')
    destination = request.form.get('destination')
    departure_date = request.form.get('departure_date')
    transport_type = request.form.get('transport_type', 'srt')

    if not departure or not destination or not departure_date:
        return jsonify({'error': '필수 입력이 누락되었습니다.'})

    # 날짜 포맷 처리
    try:
        if '-' in departure_date:
            dep_date = datetime.strptime(departure_date, '%Y-%m-%d').date()
            bus_date = departure_date.replace('-', '')
        else:
            dep_date = datetime.strptime(departure_date, '%Y%m%d').date()
            bus_date = departure_date
    except:
        dep_date = datetime.today().date()
        bus_date = dep_date.strftime('%Y%m%d')

    result = {'search_info': {
        'departure': departure,
        'destination': destination,
        'departure_date': departure_date,
        'transport_type': transport_type
    }}

    if transport_type in ['ktx', 'ktx_srt']:
        # KTX/SRT 조회 로직 (TAGO API 사용)
        try:
            # 출발지/도착지 역 코드 찾기
            dep_code = KTX_STATION_CODES.get(departure)
            arr_code = KTX_STATION_CODES.get(destination)
            
            if not dep_code or not arr_code:
                return jsonify({'error': f'지원하지 않는 역입니다. 출발지: {departure}, 도착지: {destination}'})
            
            # TAGO API 호출
            base_url = 'http://apis.data.go.kr/1613000/TrainInfoService/getStrtpntAlocFndTrainInfo'
            params = {
                'serviceKey': TAGO_API_KEY,
                'pageNo': 1,
                'numOfRows': 100,
                '_type': 'json',
                'depPlaceId': dep_code,
                'arrPlaceId': arr_code,
                'depPlandTime': bus_date
            }
            
            print(f"[DEBUG] TAGO API 요청: {base_url} params={params}")
            resp = requests.get(base_url, params=params, timeout=10)
            print(f"[DEBUG] TAGO API 응답 상태: {resp.status_code}")
            
            if resp.status_code != 200:
                print(f"[DEBUG] TAGO API 오류 응답: {resp.text}")
                # API 오류 시 샘플 데이터 반환
                trains = get_sample_train_data()
                result['ktx'] = trains
                result['ktx_srt'] = trains
                return jsonify(result)
            
            data = resp.json()
            items = data.get('response', {}).get('body', {}).get('items', {}).get('item', [])
            
            if not items:
                print("[DEBUG] TAGO API에서 결과 없음, 샘플 데이터 반환")
                trains = get_sample_train_data()
                result['ktx'] = trains
                result['ktx_srt'] = trains
                return jsonify(result)
            
            if isinstance(items, dict):
                items = [items]
            
            trains = []
            for item in items:
                dep_time = item.get('depPlandTime', '') or item.get('depplandtime', '')
                arr_time = item.get('arrPlandTime', '') or item.get('arrplandtime', '')
                price = item.get('adultCharge') or item.get('adultcharge', 50000)
                if dep_time and arr_time:
                    dep_time_str = str(dep_time)
                    arr_time_str = str(arr_time)
                    if len(dep_time_str) >= 12:
                        dep_time = f"{dep_time_str[8:10]}:{dep_time_str[10:12]}"
                    if len(arr_time_str) >= 12:
                        arr_time = f"{arr_time_str[8:10]}:{arr_time_str[10:12]}"
                    trains.append({
                        'type': item.get('trainGradeName', 'KTX') or item.get('traingradename', 'KTX'),
                        'train_no': item.get('trainNo', '') or item.get('trainno', ''),
                        'departure_time': dep_time,
                        'arrival_time': arr_time,
                        'departure': item.get('depPlaceName') or item.get('depplacename', departure),
                        'arrival': item.get('arrPlaceName') or item.get('arrplacename', destination),
                        'price': f"{int(price):,}원",
                        'available': True,
                        'seat_info': '예약가능'
                    })
            
            if not trains:
                trains = get_sample_train_data()
            
            result['ktx'] = trains
            result['ktx_srt'] = trains
            print(f"KTX/SRT 검색 결과: {len(trains)}개 열차")
            
        except Exception as e:
            print(f"[DEBUG] KTX/SRT API 오류: {e}")
            # 오류 시 샘플 데이터 반환
            trains = get_sample_train_data()
            result['ktx'] = trains
            result['ktx_srt'] = trains
        
        return jsonify(result)
        
    elif transport_type == 'bus':
        # 버스 조회 로직 (API_KEY 사용)
        try:
            # all_terminal_codes.json에서 터미널 ID 찾기
            with open(os.path.join(os.path.dirname(__file__), 'all_terminal_codes.json'), encoding='utf-8') as f:
                terminal_data = json.load(f)
            
            # 터미널명으로 터미널 ID 찾기
            dep_terminal = next((t for t in terminal_data if t['터미널명'] == departure), None)
            arr_terminal = next((t for t in terminal_data if t['터미널명'] == destination), None)
            
            if not dep_terminal or not arr_terminal:
                return jsonify({'error': f'지원하지 않는 터미널입니다. 출발지: {departure}, 도착지: {destination}'})
            
            dep_id = dep_terminal['터미널ID']
            arr_id = arr_terminal['터미널ID']
            
            print(f"[DEBUG] 터미널 ID - 출발지: {departure}({dep_id}), 도착지: {destination}({arr_id})")
            
            # 버스 API 호출
            base_url = 'http://apis.data.go.kr/1613000/ExpBusInfoService/getStrtpntAlocFndExpbusInfo'
            params = {
                'serviceKey': API_KEY,
                'depTerminalId': dep_id,
                'arrTerminalId': arr_id,
                'depPlandTime': bus_date,
                'numOfRows': 100,
                'pageNo': 1,
                '_type': 'json'
            }
            print(f"[DEBUG] 버스 API 요청: {base_url}")
            print(f"[DEBUG] 버스 API 파라미터: {params}")
            print(f"[DEBUG] API_KEY: {API_KEY[:20]}...")
            resp = requests.get(base_url, params=params, timeout=10)
            print(f"[DEBUG] 버스 API 응답 상태: {resp.status_code}")
            print(f"[DEBUG] 버스 API 응답 헤더: {dict(resp.headers)}")
            
            if resp.status_code != 200:
                print(f"[DEBUG] 버스 API 오류 응답: {resp.text}")
                # API 오류 시 샘플 데이터 반환
                buses = get_sample_bus_data()
                result['bus'] = buses
                return jsonify(result)
            
            data = resp.json()
            print(f"[DEBUG] 버스 API 응답 데이터: {json.dumps(data, indent=2, ensure_ascii=False)[:1000]}")
            
            items = data.get('response', {}).get('body', {}).get('items', {}).get('item', [])
            print(f"[DEBUG] 버스 API items: {items}")
            
            if not items:
                print("[DEBUG] 버스 API에서 결과 없음, 샘플 데이터 반환")
                buses = get_sample_bus_data()
                result['bus'] = buses
                return jsonify(result)
            
            if isinstance(items, dict):
                items = [items]
            
            buses = []
            for item in items:
                dep_time = item.get('depPlandTime', '')
                arr_time = item.get('arrPlandTime', '')
                if dep_time and arr_time:
                    # 시간 포맷 변환 (YYYYMMDDHHMM -> HH:MM)
                    dep_time_str = str(dep_time)
                    arr_time_str = str(arr_time)
                    
                    # YYYYMMDDHHMM 형식에서 HH:MM 추출
                    if len(dep_time_str) >= 10:
                        dep_time = f"{dep_time_str[8:10]}:{dep_time_str[10:12]}"
                    if len(arr_time_str) >= 10:
                        arr_time = f"{arr_time_str[8:10]}:{arr_time_str[10:12]}"
                    
                    buses.append({
                        'company': item.get('companyNm', ''),
                        'departure_time': dep_time,
                        'arrival_time': arr_time,
                        'price': f"{item.get('charge', 25000):,}원",
                        'available': True
                    })
            
            if not buses:
                buses = get_sample_bus_data()
            
            result['bus'] = buses
            print(f"버스 검색 결과: {len(buses)}개 버스")
            
        except Exception as e:
            print(f"[DEBUG] 버스 API 오류: {e}")
            # 오류 시 샘플 데이터 반환
            buses = get_sample_bus_data()
            result['bus'] = buses
        
        return jsonify(result)
    else:
        return jsonify({'error': '지원하지 않는 교통수단입니다.'})

def get_sample_train_data():
    """샘플 열차 데이터 생성"""
    base_time_ktx = [('07:30', '11:00'), ('09:00', '12:30'), ('11:00', '14:30'), ('13:00', '16:30'), ('15:30', '19:00')]
    trains = []
    for i, (dep_time, arr_time) in enumerate(base_time_ktx):
        available = i < 3  # 처음 3개는 예약 가능
        trains.append({
            'type': 'KTX',
            'train_no': f'KTX{101 + i}',
            'departure_time': dep_time,
            'arrival_time': arr_time,
            'price': f'{55000 + i*2000:,}원',
            'available': available,
            'seat_info': '예약가능' if available else '매진'
        })
    return trains

# 샘플 버스 데이터 생성 함수 개선
from datetime import datetime

def get_sample_bus_data(date=None, dep=None, arr=None):
    today_str = datetime.today().strftime('%Y-%m-%d') if date is None else date
    header = f"{dep or '출발지'} → {arr or '도착지'} 고속버스 시간표 ({today_str} 기준)"
    bus_companies = ['금고고속', '동양고속', '한진고속']
    buses = []
    for i, company in enumerate(bus_companies):
        dep_time = f"{8 + i*2:02d}:00"
        arr_time = f"{12 + i*2:02d}:30"
        buses.append({
            'company': company,
            'departure_time': dep_time,
            'arrival_time': arr_time,
            'price': f'{25000 + i*3000:,}원',
            'available': True
        })
    return {'header': header, 'buses': buses}

# 즐겨찾기 추가
@app.route('/api/save_favorite', methods=['POST'])
@login_required
def save_favorite():
    data = request.get_json()
    departure = data.get('departure')
    arrival = data.get('arrival')
    transport_type = data.get('transport_type', '기본')
    if not departure or not arrival:
        return jsonify({'success': False, 'message': '출발지와 도착지를 입력해주세요.'})
    existing = Favorite.query.filter_by(
        user_id=current_user.id,
        departure=departure,
        arrival=arrival,
        transport_type=transport_type
    ).first()
    if existing:
        return jsonify({'success': False, 'message': '이미 즐겨찾기에 추가된 경로입니다.'})
    favorite = Favorite(
        user_id=current_user.id,
        departure=departure,
        arrival=arrival,
        transport_type=transport_type
    )
    db.session.add(favorite)
    db.session.commit()
    return jsonify({'success': True, 'message': '즐겨찾기에 추가되었습니다.'})

# 즐겨찾기 삭제
@app.route('/api/favorite/<int:favorite_id>', methods=['DELETE'])
@login_required
def delete_favorite(favorite_id):
    favorite = Favorite.query.filter_by(id=favorite_id, user_id=current_user.id).first()
    if not favorite:
        return jsonify({'success': False, 'message': '즐겨찾기를 찾을 수 없습니다.'})
    db.session.delete(favorite)
    db.session.commit()
    return jsonify({'success': True, 'message': '즐겨찾기가 삭제되었습니다.'})

# 즐겨찾기 수정
@app.route('/api/favorite/<int:favorite_id>', methods=['PUT'])
@login_required
def update_favorite(favorite_id):
    data = request.get_json()
    departure = data.get('departure')
    arrival = data.get('arrival')
    transport_type = data.get('transport_type')
    favorite = Favorite.query.filter_by(id=favorite_id, user_id=current_user.id).first()
    if not favorite:
        return jsonify({'success': False, 'message': '즐겨찾기를 찾을 수 없습니다.'})
    existing = Favorite.query.filter(
        Favorite.user_id == current_user.id,
        Favorite.departure == departure,
        Favorite.arrival == arrival,
        Favorite.transport_type == transport_type,
        Favorite.id != favorite_id
    ).first()
    if existing:
        return jsonify({'success': False, 'message': '이미 존재하는 즐겨찾기입니다.'})
    favorite.departure = departure
    favorite.arrival = arrival
    favorite.transport_type = transport_type
    db.session.commit()
    return jsonify({'success': True, 'message': '즐겨찾기가 수정되었습니다.'})

@app.route('/api/search_from_favorite', methods=['POST'])
def search_from_favorite():
    """즐겨찾기에서 바로 검색"""
    try:
        data = request.get_json()
        departure = data.get('departure')
        destination = data.get('destination')
        
        if not departure or not destination:
            return jsonify({'error': '출발지와 도착지가 필요합니다.'})
        
        # 오늘 날짜로 검색
        today = datetime.today().date()
        bus_date = today.strftime('%Y-%m-%d')
        
        # KTX/SRT 검색
        trains = []
        try:
            dep_code = KTX_STATION_CODES.get(departure)
            arr_code = KTX_STATION_CODES.get(destination)
            
            if dep_code and arr_code:
                base_url = 'http://apis.data.go.kr/1613000/TrainInfoService/getStrtpntAlocFndTrainInfo'
                params = {
                    'serviceKey': TAGO_API_KEY,
                    'pageNo': 1,
                    'numOfRows': 100,
                    '_type': 'json',
                    'depPlaceId': dep_code,
                    'arrPlaceId': arr_code,
                    'depPlandTime': bus_date
                }
                
                resp = requests.get(base_url, params=params, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                    
                    if items:
                        if isinstance(items, dict):
                            items = [items]
                        
                        for item in items:
                            dep_time = item.get('depPlandTime', '')
                            arr_time = item.get('arrPlandTime', '')
                            if dep_time and arr_time:
                                dep_time = f"{dep_time[:2]}:{dep_time[2:4]}"
                                arr_time = f"{arr_time[:2]}:{arr_time[2:4]}"
                                
                                trains.append({
                                    'type': item.get('trainGradeName', 'KTX'),
                                    'train_no': item.get('trainNo', ''),
                                    'departure_time': dep_time,
                                    'arrival_time': arr_time,
                                    'price': f"{item.get('adultcharge', 50000):,}원",
                                    'available': True,
                                    'seat_info': '예약가능'
                                })
        except Exception as e:
            print(f"즐겨찾기 KTX/SRT 검색 오류: {e}")
        
        # 버스 검색
        buses = []
        try:
            # all_terminal_codes.json에서 터미널 ID 찾기
            with open(os.path.join(os.path.dirname(__file__), 'all_terminal_codes.json'), encoding='utf-8') as f:
                terminal_data = json.load(f)
            # 터미널명으로 터미널 ID 찾기
            dep_terminal = next((t for t in terminal_data if t['터미널명'] == departure), None)
            arr_terminal = next((t for t in terminal_data if t['터미널명'] == destination), None)
            if dep_terminal and arr_terminal:
                dep_id = dep_terminal['터미널ID']
                arr_id = arr_terminal['터미널ID']
                base_url = 'http://apis.data.go.kr/1613000/ExpBusInfoService/getStrtpntAlocFndExpbusInfo'
                params = {
                    'serviceKey': API_KEY,
                    'depTerminalId': dep_id,
                    'arrTerminalId': arr_id,
                    'depPlandTime': bus_date,
                    'numOfRows': 100,
                    'pageNo': 1,
                    '_type': 'json'
                }
                resp = requests.get(base_url, params=params, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                    
                    if items:
                        if isinstance(items, dict):
                            items = [items]
                        
                        for item in items:
                            dep_time = item.get('depPlandTime', '')
                            arr_time = item.get('arrPlandTime', '')
                            if dep_time and arr_time:
                                dep_time = f"{dep_time[8:10]}:{dep_time[10:12]}" if len(dep_time) >= 12 else dep_time
                                arr_time = f"{arr_time[8:10]}:{arr_time[10:12]}" if len(arr_time) >= 12 else arr_time
                                buses.append(f"{dep_time}~{arr_time} {item.get('companyNm', '')} 버스")
        except Exception as e:
            print(f"즐겨찾기 버스 검색 오류: {e}")
        
        # 결과가 없으면 샘플 데이터 반환
        if not trains:
            trains = get_sample_train_data()
        if not buses:
            buses = get_sample_bus_data()

        return jsonify({
            'success': True,
            'ktx_srt': trains,
            'bus': buses,
            'search_info': {
                'departure': departure,
                'destination': destination,
                'departure_date': today.strftime('%Y-%m-%d')
            }
        })

    except Exception as e:
        print(f"즐겨찾기 검색 오류: {e}")
        return jsonify({'success': False, 'error': '검색 중 오류가 발생했습니다.'})

@app.route('/api/booking/<string:booking_id>')
@login_required
def get_booking_detail(booking_id):
    try:
        # 기존 SQLAlchemy 모델 및 관련 코드들은 삭제 또는 주석 처리
        # 예매 정보는 데이터베이스에 저장되지 않으므로 샘플 데이터 또는 예외 처리
        # 실제 애플리케이션에서는 데이터베이스에 저장하고 조회해야 합니다.
        # 여기서는 예외를 발생시키거나 샘플 데이터를 반환합니다.
        # 예외 발생 시 실제 데이터베이스 조회 로직으로 대체 필요
        raise NotImplementedError("예매 상세 조회는 현재 구현되지 않았습니다.")
        
    except Exception as e:
        print(f"예매 정보 조회 오류: {e}")
        return jsonify({'success': False, 'message': '예매 정보 조회 중 오류가 발생했습니다.'})

@app.route('/update_profile', methods=['POST'])
@login_required
def update_profile():
    try:
        email = request.form.get('email')
        name = request.form.get('name')
        phone = request.form.get('phone')

        user = User.query.get(current_user.id)
        if user:
            user.email = email
            user.name = name
            user.phone = phone
            db.session.commit()
            flash('프로필이 성공적으로 업데이트되었습니다.', 'success')
        else:
            flash('사용자를 찾을 수 없습니다.', 'error')

    except Exception as e:
        print(f"프로필 업데이트 오류: {e}")
        flash('프로필 업데이트 중 오류가 발생했습니다.', 'error')

    return redirect(url_for('mypage'))

@app.route('/change_password', methods=['POST'])
@login_required
def change_password():
    try:
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if not current_password or not new_password or not confirm_password:
            flash('모든 필드를 입력해주세요.', 'error')
            return redirect(url_for('mypage'))

        user = User.query.get(current_user.id)
        if user and user.check_password(current_password):
            user.set_password(new_password)
            db.session.commit()
            flash('비밀번호가 성공적으로 변경되었습니다.', 'success')
        else:
            flash('현재 비밀번호가 올바르지 않습니다.', 'error')
            return redirect(url_for('mypage'))

    except Exception as e:
        print(f"비밀번호 변경 오류: {e}")
        flash('비밀번호 변경 중 오류가 발생했습니다.', 'error')

    return redirect(url_for('mypage'))

# Gemini API 키 설정
GEMINI_API_KEY = 'AIzaSyAjyQu-bO4x6BD4YK81nst11TYxWwfHDNQ'
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-2.0-flash')

# TAGO API 키 설정 (국토교통부 열차정보 API)
TAGO_API_KEY = 'TaVMa14CGsWYpQE9wR0j6ksJlGbaQ1mSGcnU+/45DrbL3tnDU8Tc0brtWZLfLJlZ8Rg7qLgImp5Y4JjkafzcAg=='

# KTX 역 코드 매핑 (실제 TAGO API 역 코드로 업데이트)
KTX_STATION_CODES = {
    '서울': 'NAT010000', '용산': 'NAT010032', '노량진': 'NAT010058', '영등포': 'NAT010091',
    '신도림': 'NAT010106', '청량리': 'NAT130126', '왕십리': 'NAT130104', '옥수': 'NAT130070',
    '서빙고': 'NAT130036', '광운대': 'NAT130182', '상봉': 'NAT020040', '수서': 'NATH30000',
    '부산': 'NAT014445', '구포': 'NAT014281', '사상': 'NAT014331', '화명': 'NAT014244',
    '부전': 'NAT750046', '동래': 'NAT750106', '센텀': 'NAT750161', '신해운대': 'NAT750189',
    '송정': 'NAT750254', '기장': 'NAT750329', '좌천': 'NAT750412',
    '대전': 'NAT011668', '서대전': 'NAT030057', '신탄진': 'NAT011524', '흑석리': 'NAT030173',
    '동대구': 'NAT013271', '대구': 'NAT013239', '서대구': 'NAT013189',
    '광주송정': 'NAT031857', '광주': 'NAT883012', '서광주': 'NAT882936', '효천': 'NAT882904',
    '울산(통도사)': 'NATH13717', '북울산': 'NAT750781', '남창': 'NAT750560', '덕하': 'NAT750653',
    '태화강': 'NAT750726', '효문': 'NAT750760'
}

def generate_gemini_response(user, message):
    """Gemini 2.5 Flash를 사용한 AI 응답 생성"""
    try:
        # (원한다면 사용자 정보 기반 프롬프트 확장 가능)
        prompt = message
        response = gemini_model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.7,
                "top_p": 0.8,
                "top_k": 40,
                "max_output_tokens": 2048,
            }
        )
        if response and response.text:
            return response.text.strip()
        else:
            return "죄송합니다. AI 응답 생성에 실패했습니다."
    except Exception as e:
        print(f"Gemini API 오류: {e}")
        return f"AI 서비스 오류: {str(e)}"

# AI 대화내역 저장 (DynamoDB)
@app.route('/api/chatbot', methods=['POST'])
def chatbot_api():
    """Gemini 2.5 Flash 기반 AI 챗봇 API + 실시간 교통편 추천"""
    try:
        from datetime import datetime, timedelta
        import re
        data = request.get_json()
        user_message = data.get('message', '').strip()
        print(f"[챗봇] 사용자 메시지: {user_message}")
        if not user_message:
            return jsonify({'success': False, 'response': '메시지를 입력해주세요.'})

        # 날짜 관련 질문 예외처리 (오늘 날짜, 지금 날짜, 현재 날짜)
        if re.search(r'(오늘|지금|현재)[\s]*(날짜|date)', user_message):
            today = datetime.today().strftime('%Y-%m-%d')
            return jsonify({'success': True, 'response': f'오늘 날짜는 {today} 입니다.'})

        # 실시간 교통편 추천 키워드 확장
        transport_keywords = ['여행', '추천', '경로', '교통편', '버스', '버스 시간표', '버스 시간']
        if any(kw in user_message for kw in transport_keywords):
            # 출발지/도착지/날짜 파싱 강화
            dep, arr, date = None, None, None
            # "A에서 B까지" 패턴
            m = re.search(r'([가-힣]+)[에서|발][ ]*([가-힣]+)[까지|행|도착]', user_message)
            if m:
                dep, arr = m.group(1), m.group(2)
            else:
                # "A-B" 패턴
                m2 = re.search(r'([가-힣]+)[-~→\->]+([가-힣]+)', user_message)
                if m2:
                    dep, arr = m2.group(1), m2.group(2)
            # 날짜 추출 ("내일", "오늘", "YYYY-MM-DD", "YYYYMMDD")
            if '내일' in user_message:
                date = (datetime.today() + timedelta(days=1)).strftime('%Y%m%d')
            elif '오늘' in user_message:
                date = datetime.today().strftime('%Y%m%d')
            else:
                m3 = re.search(r'(20\d{2}-\d{2}-\d{2})', user_message)
                if m3:
                    date = m3.group(1).replace('-', '')
                else:
                    m4 = re.search(r'(20\d{6})', user_message)
                    if m4:
                        date = m4.group(1)
            if not date:
                date = datetime.today().strftime('%Y%m%d')
            if not dep or not arr:
                ai_response = generate_gemini_response(current_user if current_user.is_authenticated else None, user_message)
                return jsonify({'success': True, 'response': ai_response})
            # strip() 적용해 공백 문제 방지
            dep = dep.strip()
            arr = arr.strip()
            # 실시간 교통편 조회
            trains = []
            buses = []
            
            # KTX/SRT 검색
            try:
                dep_code = KTX_STATION_CODES.get(dep)
                arr_code = KTX_STATION_CODES.get(arr)
                
                if dep_code and arr_code:
                    base_url = 'http://apis.data.go.kr/1613000/TrainInfoService/getStrtpntAlocFndTrainInfo'
                    params = {
                        'serviceKey': TAGO_API_KEY,
                        'pageNo': 1,
                        'numOfRows': 100,
                        '_type': 'json',
                        'depPlaceId': dep_code,
                        'arrPlaceId': arr_code,
                        'depPlandTime': date
                    }
                    
                    resp = requests.get(base_url, params=params, timeout=10)
                    if resp.status_code == 200:
                        data = resp.json()
                        items = data.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                        
                        if items:
                            if isinstance(items, dict):
                                items = [items]
                            
                            for item in items[:3]:  # 상위 3개만
                                dep_time = item.get('depPlandTime', '')
                                arr_time = item.get('arrPlandTime', '')
                                if dep_time and arr_time:
                                    dep_time = f"{dep_time[:2]}:{dep_time[2:4]}"
                                    arr_time = f"{arr_time[:2]}:{arr_time[2:4]}"
                                    
                                    trains.append({
                                        'type': item.get('trainGradeName', 'KTX'),
                                        'train_no': item.get('trainNo', ''),
                                        'departure_time': dep_time,
                                        'arrival_time': arr_time,
                                        'price': f"{item.get('adultcharge', 50000):,}원",
                                        'available': True,
                                        'seat_info': '예약가능'
                                    })
            except Exception as e:
                print(f"챗봇 KTX/SRT 검색 오류: {e}")
            
            # 버스 검색
            try:
                with open(os.path.join(os.path.dirname(__file__), 'all_terminal_codes.json'), encoding='utf-8') as f:
                    terminal_data = json.load(f)
                dep_terminal = next((t for t in terminal_data if t['터미널명'].strip() == dep), None)
                arr_terminal = next((t for t in terminal_data if t['터미널명'].strip() == arr), None)
                if not dep_terminal or not arr_terminal:
                    print(f"[ERROR] 터미널명 매칭 실패: dep={dep}, arr={arr}")
                    sample = get_sample_bus_data(date=datetime.strptime(date, '%Y%m%d').strftime('%Y-%m-%d'), dep=dep, arr=arr)
                    answer = f"{sample['header']}\n(실제 시간표는 예매사이트에서 확인하세요)"
                    for bus in sample['buses']:
                        answer += f"\n- {bus['departure_time']}~{bus['arrival_time']} {bus['company']} {bus['price']}"
                    return jsonify({'success': True, 'response': answer})
                dep_id = dep_terminal['터미널ID']
                arr_id = arr_terminal['터미널ID']
                base_url = 'http://apis.data.go.kr/1613000/ExpBusInfoService/getStrtpntAlocFndExpbusInfo'
                params = {
                    'serviceKey': API_KEY,
                    'depTerminalId': dep_id,
                    'arrTerminalId': arr_id,
                    'depPlandTime': date,
                    'numOfRows': 100,
                    'pageNo': 1,
                    '_type': 'json'
                }
                print(f"[DEBUG] 버스 API 요청: {base_url}")
                print(f"[DEBUG] 버스 API 파라미터: {params}")
                print(f"[DEBUG] API_KEY: {API_KEY[:20]}...")
                resp = requests.get(base_url, params=params, timeout=10)
                print(f"[DEBUG] 버스 API 응답 상태: {resp.status_code}")
                print(f"[DEBUG] 버스 API 응답 헤더: {dict(resp.headers)}")
                if resp.status_code != 200:
                    print(f"[DEBUG] 버스 API 오류 응답: {resp.text}")
                    sample = get_sample_bus_data(date=datetime.strptime(date, '%Y%m%d').strftime('%Y-%m-%d'), dep=dep, arr=arr)
                    answer = f"{sample['header']}\n(실제 시간표는 예매사이트에서 확인하세요)"
                    for bus in sample['buses']:
                        answer += f"\n- {bus['departure_time']}~{bus['arrival_time']} {bus['company']} {bus['price']}"
                    return jsonify({'success': True, 'response': answer})
                data = resp.json()
                print(f"[DEBUG] 버스 API 응답 데이터: {json.dumps(data, indent=2, ensure_ascii=False)[:1000]}")
                items = data.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                print(f"[DEBUG] 버스 API items: {items}")
                if not items:
                    print("[DEBUG] 버스 API에서 결과 없음, 샘플 데이터 반환")
                    sample = get_sample_bus_data(date=datetime.strptime(date, '%Y%m%d').strftime('%Y-%m-%d'), dep=dep, arr=arr)
                    answer = f"{sample['header']}\n(실제 시간표는 예매사이트에서 확인하세요)"
                    for bus in sample['buses']:
                        answer += f"\n- {bus['departure_time']}~{bus['arrival_time']} {bus['company']} {bus['price']}"
                    return jsonify({'success': True, 'response': answer})
                if isinstance(items, dict):
                    items = [items]
                for item in items[:3]:  # 상위 3개만
                    dep_time = item.get('depPlandTime', '')
                    arr_time = item.get('arrPlandTime', '')
                    if dep_time and arr_time:
                        dep_time = f"{dep_time[8:10]}:{dep_time[10:12]}" if len(dep_time) >= 12 else dep_time
                        arr_time = f"{arr_time[8:10]}:{arr_time[10:12]}" if len(arr_time) >= 12 else arr_time
                        buses.append(f"{dep_time}~{arr_time} {item.get('companyNm', '')} 버스")
            except Exception as e:
                print(f"챗봇 버스 검색 오류: {e}")
            if not buses:
                sample = get_sample_bus_data(date=datetime.strptime(date, '%Y%m%d').strftime('%Y-%m-%d'), dep=dep, arr=arr)
                answer = f"{sample['header']}\n(실제 시간표는 예매사이트에서 확인하세요)"
                for bus in sample['buses']:
                    answer += f"\n- {bus['departure_time']}~{bus['arrival_time']} {bus['company']} {bus['price']}"
                return jsonify({'success': True, 'response': answer})
            answer = f"{dep} → {arr} ({format_date(date)})\n"
            if trains:
                answer += "\n[기차]"
                for t in trains[:2]:
                    answer += f"\n- {t.get('type','')} {t.get('departure_time','')}~{t.get('arrival_time','')} {t.get('price','')}"
            if buses:
                answer += "\n[고속버스]"
                for b in buses:
                    answer += f"\n- {b}"
            if not trains and not buses:
                answer += "\n(해당 날짜에 조회된 교통편이 없습니다.)"
            return jsonify({'success': True, 'response': answer})

        # 그 외는 Gemini AI로 처리
        ai_response = generate_gemini_response(current_user if current_user.is_authenticated else None, user_message)
        print(f"[챗봇] Gemini 응답: {ai_response}")

        # (로그인한 경우 대화 기록 저장)
        if current_user.is_authenticated:
            try:
                chat_record = {
                    'user_id': str(current_user.id),
                    'message': user_message,
                    'response': ai_response,
                    'timestamp': int(time.time())
                }
                chat_table.put_item(Item=chat_record)
            except Exception as e:
                print(f"채팅 기록 저장 오류: {e}")

        return jsonify({'success': True, 'response': ai_response})

    except Exception as e:
        print(f"[챗봇] 챗봇 API 오류: {e}")
        return jsonify({'success': False, 'response': 'AI 서비스 오류가 발생했습니다.'})

@app.route('/api/chat_history')
@login_required
def get_chat_history():
    """사용자의 채팅 기록 조회"""
    try:
        from boto3.dynamodb.conditions import Key
        history = list(chat_table.query(
            KeyConditionExpression=Key('user_id').eq(str(current_user.id)),
            ScanIndexForward=False,
            Limit=50
        )['Items'])
        
        chat_data = []
        for chat in history:
            # timestamp가 decimal.Decimal일 수 있으므로 float으로 변환
            ts = chat['timestamp']
            try:
                ts_val = float(ts)
            except Exception:
                ts_val = 0
            chat_data.append({
                'message': chat['message'],
                'response': chat['response'],
                'timestamp': datetime.fromtimestamp(ts_val).strftime('%Y-%m-%d %H:%M')
            })
        
        return jsonify({
            'success': True,
            'history': chat_data
        })
        
    except Exception as e:
        print(f"채팅 기록 조회 오류: {e}")
        return jsonify({
            'success': False,
            'history': []
        })

@app.route('/redirect_booking')
def redirect_booking():
    """외부 예매 사이트로 리다이렉트"""
    transport_type = request.args.get('type', '').lower()
    
    urls = {
        'ktx': 'https://www.korail.com/ticket/main',
        'srt': 'https://etk.srail.kr/hpg/hra/01/selectScheduleList.do',
        'bus': 'https://www.kobus.co.kr/main.do'
    }
    
    url = urls.get(transport_type, 'https://www.letskorail.com')
    return redirect(url)

# 샘플 예매 데이터 생성 (개발용)
@app.route('/api/create_sample_booking', methods=['POST'])
@login_required
def create_sample_booking():
    """개발용: 샘플 예매 데이터 생성"""
    try:
        # 기존 SQLAlchemy 모델 및 관련 코드들은 삭제 또는 주석 처리
        # 예매 정보는 데이터베이스에 저장되지 않으므로 샘플 데이터 또는 예외 처리
        # 실제 애플리케이션에서는 데이터베이스에 저장하고 조회해야 합니다.
        # 여기서는 예외를 발생시키거나 샘플 데이터를 반환합니다.
        # 예외 발생 시 실제 데이터베이스 조회 로직으로 대체 필요
        raise NotImplementedError("샘플 예매 데이터 생성은 현재 구현되지 않았습니다.")
        
    except Exception as e:
        print(f"샘플 데이터 생성 오류: {e}")
        return jsonify({'success': False, 'message': '샘플 데이터 생성 중 오류가 발생했습니다.'})

# 관리자용 데이터베이스 초기화
@app.route('/api/init_db')
def init_database():
    """데이터베이스 테이블 생성"""
    try:
        # 기존 SQLAlchemy 모델 및 관련 코드들은 삭제 또는 주석 처리
        # 데이터베이스 초기화는 데이터베이스 연결 방식에 따라 다릅니다.
        # 여기서는 예시로 데이터베이스 테이블 생성을 시도합니다.
        # 실제 MongoDB는 컬렉션 생성 시 데이터베이스 존재 여부를 확인하지 않으므로 오류 발생 시 무시
        try:
            db.create_all() # SQLAlchemy 테이블 생성
            print("SQLAlchemy 테이블 생성 시도")
        except Exception as e:
            print(f"SQLAlchemy 테이블 생성 오류 (이미 존재할 수 있음): {e}")

        try:
            dynamodb.create_table(
                TableName=Config.DYNAMODB_TABLE,
                KeySchema=[
                    {'AttributeName': 'user_id', 'KeyType': 'HASH'},
                    {'AttributeName': 'timestamp', 'KeyType': 'RANGE'}
                ],
                AttributeDefinitions=[
                    {'AttributeName': 'user_id', 'AttributeType': 'S'},
                    {'AttributeName': 'timestamp', 'AttributeType': 'N'}
                ],
                ProvisionedThroughput={
                    'ReadCapacityUnits': 5,
                    'WriteCapacityUnits': 5
                }
            )
            print("DynamoDB 테이블 생성 시도")
        except Exception as e:
            print(f"DynamoDB 테이블 생성 오류 (이미 존재할 수 있음): {e}")

        return jsonify({'success': True, 'message': '데이터베이스가 초기화되었습니다.'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'데이터베이스 초기화 오류: {str(e)}'})

# 에러 핸들러
@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    # 기존 SQLAlchemy 모델 및 관련 코드들은 삭제 또는 주석 처리
    # 데이터베이스 세션 롤백은 데이터베이스 연결 방식에 따라 다릅니다.
    # 여기서는 예시로 시도합니다.
    try:
        # 실제 MongoDB는 세션 관리가 필요하지 않으므로 이 부분은 무시
        # 또는 데이터베이스 연결 방식에 따라 다르게 처리
        pass # MongoDB에서는 세션 관리가 없으므로 이 부분은 무시
    except Exception as e:
        print(f"데이터베이스 세션 롤백 오류: {e}")
    return render_template('500.html'), 500

# 컨텍스트 프로세서 - 템플릿에서 사용할 전역 변수
@app.context_processor
def inject_global_vars():
    return {
        'current_year': datetime.now().year,
        'app_name': 'AI 여행계획',
        'app_version': '1.0.0'
    }

API_KEY = 'TaVMa14CGsWYpQE9wR0j6ksJlGbaQ1mSGcnU+/45DrbL3tnDU8Tc0brtWZLfLJlZ8Rg7qLgImp5Y4JjkafzcAg=='  # URL-encoded 인증키 사용

# 터미널 코드 로드
with open(os.path.join(os.path.dirname(__file__), 'all_terminal_codes.json'), encoding='utf-8') as f:
    TERMINALS = json.load(f)

@app.route('/api/stations')
def get_stations():
    try:
        base_url = 'http://apis.data.go.kr/1613000/TrainInfoService/getCtyAcctoTrainSttnList'
        api_key = TAGO_API_KEY
        print("[DEBUG] TAGO_API_KEY:", api_key)
        stations = []
        city_codes = [11, 21, 25, 24, 22, 26]  # 서울, 부산, 대전, 광주, 대구, 울산
        for city_code in city_codes:
            params = {
                'serviceKey': api_key,
                'pageNo': 1,
                'numOfRows': 100,
                '_type': 'json',
                'cityCode': city_code
            }
            print(f"[DEBUG] API 요청: {base_url} params={params}")
            resp = requests.get(base_url, params=params, timeout=10)
            print("[DEBUG] API 응답:", resp.text[:500])
            data = resp.json()
            items = data.get('response', {}).get('body', {}).get('items', {}).get('item', [])
            if isinstance(items, dict):
                items = [items]
            for item in items:
                stations.append({
                    'name': item.get('stationName') or item.get('nodename'),
                    'code': item.get('stationCode') or item.get('nodeid')
                })
        # 중복 제거 (역 이름 기준)
        unique_stations = {s['name']: s for s in stations}.values()
        return jsonify({'success': True, 'stations': list(unique_stations)})
    except Exception as e:
        print(f"[DEBUG] 역 목록 API 오류: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/bus_terminals')
def get_bus_terminals():
    """버스 터미널 목록 제공"""
    try:
        # all_terminal_codes.json 파일에서 터미널 목록 로드
        with open(os.path.join(os.path.dirname(__file__), 'all_terminal_codes.json'), encoding='utf-8') as f:
            terminals = json.load(f)
        
        # 터미널명으로 정렬
        terminals.sort(key=lambda x: x['터미널명'])
        
        return jsonify({
            'success': True, 
            'terminals': terminals
        })
    except Exception as e:
        print(f"[DEBUG] 버스 터미널 목록 로드 오류: {e}")
        return jsonify({
            'success': False, 
            'error': str(e),
            'terminals': []
        })

@app.route('/bus', methods=['GET', 'POST'])
def bus():
    results = []
    error = None
    # all_terminal_codes.json에서 터미널명 목록 가져오기
    terminal_names = sorted([t['터미널명'] for t in TERMINALS])
    
    if request.method == 'POST':
        dep = request.form['departure']
        arr = request.form['arrival']
        date = request.form['date'].replace('-', '')  # YYYYMMDD
        
        # 터미널명으로 터미널 ID 찾기
        dep_terminal = next((t for t in TERMINALS if t['터미널명'] == dep), None)
        arr_terminal = next((t for t in TERMINALS if t['터미널명'] == arr), None)
        
        if not dep_terminal or not arr_terminal:
            error = '출발지 또는 도착지 터미널명이 올바르지 않습니다.'
        else:
            dep_id = dep_terminal['터미널ID']
            arr_id = arr_terminal['터미널ID']
            
            base_url = 'http://apis.data.go.kr/1613000/ExpBusInfoService/getStrtpntAlocFndExpbusInfo'
            params = {
                'depTerminalId': dep_id,
                'arrTerminalId': arr_id,
                'depPlandTime': date,
                'numOfRows': 100,
                'pageNo': 1,
                '_type': 'json'
            }
            url = f"{base_url}?serviceKey={API_KEY}"
            try:
                resp = requests.get(url, params=params, timeout=10)
                with open("bus_api_debug.txt", "w", encoding="utf-8") as f:
                    f.write(resp.text)
                try:
                    data = resp.json()
                except Exception:
                    error = f'API 응답이 JSON이 아님: {resp.text[:500]}'
                    return render_template('bus.html', results=[], error=error, terminals=terminal_names)
                items = data.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                if not items:
                    error = '조회 결과가 없습니다.'
                else:
                    if isinstance(items, dict):
                        items = [items]
                    for item in items:
                        results.append({
                            'depTime': item.get('depPlandTime', ''),
                            'grade': item.get('gradeNm', ''),
                            'charge': item.get('charge', ''),
                            'company': item.get('companyNm', ''),
                        })
            except Exception as e:
                error = f'API 오류: {e}'
    return render_template('bus.html', results=results, error=error, terminals=terminal_names)

@app.route('/api/test_tago')
def test_tago_api():
    """TAGO API 테스트용 라우트"""
    try:
        # 실제 API 테스트
        today = datetime.today().strftime('%Y%m%d')
        
        # KTX/SRT API 테스트 (서울-부산)
        ktx_test_result = None
        try:
            dep_code = KTX_STATION_CODES.get('서울')
            arr_code = KTX_STATION_CODES.get('부산')
            
            if dep_code and arr_code:
                base_url = 'http://apis.data.go.kr/1613000/TrainInfoService/getStrtpntAlocFndTrainInfo'
                params = {
                    'serviceKey': TAGO_API_KEY,
                    'pageNo': 1,
                    'numOfRows': 10,
                    '_type': 'json',
                    'depPlaceId': dep_code,
                    'arrPlaceId': arr_code,
                    'depPlandTime': today
                }
                
                resp = requests.get(base_url, params=params, timeout=10)
                ktx_test_result = {
                    'status_code': resp.status_code,
                    'response': resp.text[:500] if resp.status_code != 200 else 'Success'
                }
        except Exception as e:
            ktx_test_result = {'error': str(e)}
        
        # 버스 API 테스트 (서울-부산)
        bus_test_result = None
        try:
            # all_terminal_codes.json에서 터미널 ID 찾기
            with open(os.path.join(os.path.dirname(__file__), 'all_terminal_codes.json'), encoding='utf-8') as f:
                terminal_data = json.load(f)
            
            # 서울경부와 부산 터미널 찾기
            dep_terminal = next((t for t in terminal_data if '서울' in t['터미널명']), None)
            arr_terminal = next((t for t in terminal_data if '부산' in t['터미널명']), None)
            
            if dep_terminal and arr_terminal:
                dep_id = dep_terminal['터미널ID']
                arr_id = arr_terminal['터미널ID']
                
                base_url = 'http://apis.data.go.kr/1613000/ExpBusInfoService/getStrtpntAlocFndExpbusInfo'
                params = {
                    'serviceKey': API_KEY,
                    'depTerminalId': dep_id,
                    'arrTerminalId': arr_id,
                    'depPlandTime': today,
                    'numOfRows': 10,
                    'pageNo': 1,
                    '_type': 'json'
                }
                
                resp = requests.get(base_url, params=params, timeout=10)
                bus_test_result = {
                    'status_code': resp.status_code,
                    'response': resp.text[:500] if resp.status_code != 200 else 'Success',
                    'dep_terminal': dep_terminal['터미널명'],
                    'arr_terminal': arr_terminal['터미널명']
                }
        except Exception as e:
            bus_test_result = {'error': str(e)}

        return jsonify({
            'success': True,
            'station_list': TERMINALS, # 역 목록 데이터
            'api_keys': {
                'TAGO_API_KEY': TAGO_API_KEY[:20] + '...' if TAGO_API_KEY else 'Not set',
                'API_KEY': API_KEY[:20] + '...' if API_KEY else 'Not set'
            },
            'test_result': {
                'ktx_api_test': ktx_test_result,
                'bus_api_test': bus_test_result,
                'sample_trains': get_sample_train_data(),
                'sample_buses': get_sample_bus_data()
            }
        })
        
    except Exception as e:
        print(f"TAGO API 테스트 오류: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/', endpoint='index')
def index():
    s3 = boto3.client(
        's3',
        region_name='ap-northeast-2',
        aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY')
    )
    bucket = 'project-trip-pic'
    prefix = 'backgrounds/'
    print("[DEBUG] S3_BUCKET:", bucket)
    print("[DEBUG] AWS_REGION:", 'ap-northeast-2')
    response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
    bg_images = []
    for obj in response.get('Contents', []):
        key = obj['Key']
        if key != prefix and not key.endswith('/'):
            bg_images.append(key)
    print("[DEBUG] bg_images:", bg_images)
    bg_image = None
    if bg_images:
        import random
        bg_image = random.choice(bg_images)
        print("[DEBUG] bg_image (random):", bg_image)
        from urllib.parse import quote
        s3_url = f"https://{bucket}.s3.ap-northeast-2.amazonaws.com/{quote(bg_image)}"
        print("[DEBUG] S3 URL:", s3_url)

    # KTX 역 목록 (KTX_STATION_CODES의 키)
    KTX_STATION_CODES = {
        '서울': 'NAT010000', '용산': 'NAT010032', '노량진': 'NAT010058', '영등포': 'NAT010091',
        '신도림': 'NAT010106', '청량리': 'NAT130126', '왕십리': 'NAT130104', '옥수': 'NAT130070',
        '서빙고': 'NAT130036', '광운대': 'NAT130182', '상봉': 'NAT020040', '수서': 'NATH30000',
        '부산': 'NAT014445', '구포': 'NAT014281', '사상': 'NAT014331', '화명': 'NAT014244',
        '부전': 'NAT750046', '동래': 'NAT750106', '센텀': 'NAT750161', '신해운대': 'NAT750189',
        '송정': 'NAT750254', '기장': 'NAT750329', '좌천': 'NAT750412',
        '대전': 'NAT011668', '서대전': 'NAT030057', '신탄진': 'NAT011524', '흑석리': 'NAT030173',
        '동대구': 'NAT013271', '대구': 'NAT013239', '서대구': 'NAT013189',
        '광주송정': 'NAT031857', '광주': 'NAT883012', '서광주': 'NAT882936', '효천': 'NAT882904',
        '울산(통도사)': 'NATH13717', '북울산': 'NAT750781', '남창': 'NAT750560', '덕하': 'NAT750653',
        '태화강': 'NAT750726', '효문': 'NAT750760'
    }
    ktx_stations = list(KTX_STATION_CODES.keys())

    # 버스 터미널 목록 (TERMINALS에서 터미널명만 추출)
    bus_terminals = [t['터미널명'] for t in TERMINALS if '터미널명' in t]

    return render_template(
        'index.html',
        bg_images=bg_images,
        ktx_stations=ktx_stations,
        bus_terminals=bus_terminals,
        # ...다른 변수들...
    )

if __name__ == '__main__':
    with app.app_context():
        # 기존 SQLAlchemy 모델 및 관련 코드들은 삭제 또는 주석 처리
        # 데이터베이스 초기화는 데이터베이스 연결 방식에 따라 다릅니다.
        # 여기서는 예시로 데이터베이스 테이블 생성을 시도합니다.
        # 실제 MongoDB는 컬렉션 생성 시 데이터베이스 존재 여부를 확인하지 않으므로 오류 발생 시 무시
        try:
            db.create_all() # SQLAlchemy 테이블 생성
            print("SQLAlchemy 테이블 생성 시도")
        except Exception as e:
            print(f"SQLAlchemy 테이블 생성 오류 (이미 존재할 수 있음): {e}")

        try:
            dynamodb.create_table(
                TableName=Config.DYNAMODB_TABLE,
                KeySchema=[
                    {'AttributeName': 'user_id', 'KeyType': 'HASH'},
                    {'AttributeName': 'timestamp', 'KeyType': 'RANGE'}
                ],
                AttributeDefinitions=[
                    {'AttributeName': 'user_id', 'AttributeType': 'S'},
                    {'AttributeName': 'timestamp', 'AttributeType': 'N'}
                ],
                ProvisionedThroughput={
                    'ReadCapacityUnits': 5,
                    'WriteCapacityUnits': 5
                }
            )
            print("DynamoDB 테이블 생성 시도")
        except Exception as e:
            print(f"DynamoDB 테이블 생성 오류 (이미 존재할 수 있음): {e}")

    app.run(debug=True, host='0.0.0.0', port=5000)