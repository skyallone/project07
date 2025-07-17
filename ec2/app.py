from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta
import requests
from bs4 import BeautifulSoup
import os
import json
import time
import google.generativeai as genai


app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///travel_planner.db'
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

class TravelPlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    departure = db.Column(db.String(100), nullable=False)
    destination = db.Column(db.String(100), nullable=False)
    departure_date = db.Column(db.Date, nullable=False)
    arrival_date = db.Column(db.Date, nullable=True)
    passengers = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('travel_plans', lazy=True))

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    transport_type = db.Column(db.String(50), nullable=False)
    departure = db.Column(db.String(100), nullable=False)
    arrival = db.Column(db.String(100), nullable=False)
    departure_time = db.Column(db.DateTime, nullable=False)
    arrival_time = db.Column(db.DateTime, nullable=True)
    price = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), default='confirmed')
    passenger_name = db.Column(db.String(100), nullable=False)
    passenger_phone = db.Column(db.String(20), nullable=False)
    passenger_count = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('bookings', lazy=True))

class Favorite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    departure = db.Column(db.String(100), nullable=False)
    arrival = db.Column(db.String(100), nullable=False)
    transport_type = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('favorites', lazy=True))

# 챗봇 대화 기록 저장용 모델
class ChatHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    message = db.Column(db.Text, nullable=False)
    response = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref=db.backref('chat_history', lazy=True))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class TransportationChecker:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ko-KR,ko;q=0.8,en-US;q=0.5,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })

        # SRT 역 코드
        self.station_codes = {
            '수서': '0551', '동탄': '0552', '천안아산': '0557', '오송': '0027',
            '대전': '0010', '김천(구미)': '0507', '동대구': '0015', '신경주': '0508',
            '울산(통도사)': '0509', '부산': '0020', '공주': '0514', '익산': '0030',
            '정읍': '0033', '광주송정': '0036', '나주': '0037', '목포': '0041',
            '서대구': '0506', '밀양': '0017', '진영': '0512', '창원중앙': '0513',
            '창원': '0511', '마산': '0019', '진주': '0515', '포항': '0508',
            '전주': '0045', '남원': '0516', '곡성': '0517', '구례구': '0518',
            '순천': '0051', '여천': '0053', '여수EXPO': '0057'
        }

    def check_ktx_srt(self, departure, destination, departure_date, arrival_date=None):
        """SRT/KTX 정보 조회 (TAGO API 사용)"""
        try:
            # KTX 정보 조회 시도
            ktx_data = self._get_ktx_info(departure, destination, departure_date)
            if ktx_data:
                return ktx_data
            
            # KTX 조회 실패 시 SRT 정보 조회 시도
            srt_data = self._get_srt_info(departure, destination, departure_date)
            if srt_data:
                return srt_data
            
            # 모두 실패 시 샘플 데이터 반환
            print("실제 API 조회 실패, 샘플 데이터 사용")
            return self._get_sample_data(departure, destination)
            
        except Exception as e:
            print(f"열차 정보 조회 오류: {e}")
            return self._get_sample_data(departure, destination)

    def _get_ktx_info(self, departure, destination, departure_date):
        """TAGO API를 사용한 KTX 정보 조회"""
        try:
            # 역 코드 확인
            dep_code = KTX_STATION_CODES.get(departure)
            arr_code = KTX_STATION_CODES.get(destination)
            
            if not dep_code or not arr_code:
                print(f"KTX 역 코드를 찾을 수 없음: {departure} -> {destination}")
                return None
            
            # 날짜 형식 변환 (YYYY-MM-DD -> YYYYMMDD)
            if isinstance(departure_date, str):
                if '-' in departure_date:
                    date_str = departure_date.replace('-', '')
                else:
                    date_str = departure_date
            else:
                date_str = departure_date.strftime('%Y%m%d')
            
            # TAGO API 호출 (국토교통부 열차정보 API)
            base_url = 'http://apis.data.go.kr/1613000/TrainInfoService/getStrtpntAlocFndTrainInfo'
            params = {
                'serviceKey': TAGO_API_KEY,
                'pageNo': 1,
                'numOfRows': 50,
                '_type': 'json',
                'depPlaceId': dep_code,
                'arrPlaceId': arr_code,
                'depPlandTime': date_str,
                'trainGradeCode': '00'  # KTX
            }
            
            print(f"TAGO API 호출: {departure}({dep_code}) -> {destination}({arr_code}) on {date_str}")
            
            response = self.session.get(base_url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            # API 응답 구조 확인
            header = data.get('response', {}).get('header', {})
            if header.get('resultCode') != '00':
                print(f"TAGO API 오류: {header.get('resultMsg')}")
                return None
            
            items = data.get('response', {}).get('body', {}).get('items', {}).get('item', [])
            
            if not items:
                print("KTX 조회 결과 없음")
                return None
            
            # 단일 결과인 경우 리스트로 변환
            if isinstance(items, dict):
                items = [items]
            
            trains = []
            for item in items:
                # 출발시간 파싱 (YYYYMMDDHHMMSS -> HH:MM)
                dep_time = str(item.get('depplandtime', ''))
                if len(dep_time) >= 12:
                    dep_time = dep_time[8:10] + ':' + dep_time[10:12]
                
                # 도착시간 파싱 (YYYYMMDDHHMMSS -> HH:MM)
                arr_time = str(item.get('arrplandtime', ''))
                if len(arr_time) >= 12:
                    arr_time = arr_time[8:10] + ':' + arr_time[10:12]
                
                # 요금 정보
                charge = item.get('adultcharge', '')
                if charge and str(charge).isdigit():
                    charge = f"{int(charge):,}원"
                
                # 열차번호
                train_no = item.get('trainno', '')
                
                # 열차종류
                train_type = item.get('traingradename', 'KTX')
                
                trains.append({
                    'type': train_type,
                    'train_no': train_no,
                    'departure_time': dep_time,
                    'arrival_time': arr_time,
                    'price': charge,
                    'available': True,
                    'seat_info': '예약가능'
                })
            
            print(f"KTX 조회 성공: {len(trains)}개 열차")
            print(f"첫 번째 열차 정보: {trains[0] if trains else 'None'}")
            return trains
            
        except Exception as e:
            print(f"KTX API 조회 오류: {e}")
            return None

  #  def _get_srt_info(self, departure, destination, departure_date):
        """SRT 정보 조회 (기존 크롤링 방식 유지)"""
        try:
            # 기존 SRT 크롤링 로직 사용
            from srt_crawler import get_srt_info_selenium
            results = get_srt_info_selenium(departure, destination, departure_date)
            
            if results:
                trains = []
                for result in results:
                    trains.append({
                        'type': 'SRT',
                        'train_no': result.get('train_no', ''),
                        'departure_time': result.get('departure_time', ''),
                        'arrival_time': result.get('arrival_time', ''),
                        'price': result.get('price', ''),
                        'available': result.get('available', True),
                        'seat_info': result.get('seat_info', '예약가능')
                    })
                return trains
            
            return None
            
        except Exception as e:
            print(f"SRT 조회 오류: {e}")
            return None

    def get_ktx_info_api(self, departure, destination, departure_date):
        """TAGO API를 사용한 KTX 정보만 조회"""
        try:
            dep_code = KTX_STATION_CODES.get(departure)
            arr_code = KTX_STATION_CODES.get(destination)
            if not dep_code or not arr_code:
                print(f"KTX 역 코드를 찾을 수 없음: {departure} -> {destination}")
                # 역 코드가 없으면 샘플 데이터 반환
                return self._get_sample_ktx_data(departure, destination)
            if isinstance(departure_date, str):
                if '-' in departure_date:
                    date_str = departure_date.replace('-', '')
                else:
                    date_str = departure_date
            else:
                date_str = departure_date.strftime('%Y%m%d')
            base_url = 'http://apis.data.go.kr/1613000/TrainInfoService/getStrtpntAlocFndTrainInfo'
            params = {
                'serviceKey': TAGO_API_KEY,
                'pageNo': 1,
                'numOfRows': 100,  # 더 많은 결과를 가져오기 위해 증가
                '_type': 'json',
                'depPlaceId': dep_code,
                'arrPlaceId': arr_code,
                'depPlandTime': date_str
                # 'trainGradeCode': '00'  # KTX만 조회하지 않고 전체 조회
            }
            print(f"TAGO API 요청 URL: {base_url}")
            print(f"TAGO API 파라미터: {params}")
            
            response = self.session.get(base_url, params=params, timeout=10)
            print(f"TAGO API 응답 상태: {response.status_code}")
            print(f"TAGO API 응답 헤더: {response.headers.get('content-type', 'unknown')}")
            
            # 응답 내용 확인
            response_text = response.text
            print(f"TAGO API 응답 내용 (처음 500자): {response_text[:500]}")
            
            if not response_text.strip():
                print("TAGO API 빈 응답")
                return self._get_sample_ktx_data(departure, destination)
            
            try:
                data = response.json()
            except json.JSONDecodeError as e:
                print(f"TAGO API JSON 파싱 오류: {e}")
                print(f"전체 응답: {response_text}")
                return self._get_sample_ktx_data(departure, destination)
            
            header = data.get('response', {}).get('header', {})
            if header.get('resultCode') != '00':
                print(f"TAGO API 오류: {header.get('resultMsg')}")
                return self._get_sample_ktx_data(departure, destination)
            items = data.get('response', {}).get('body', {}).get('items', {})
            if not items or isinstance(items, str):
                print("TAGO API 조회 결과 없음, 샘플 데이터 사용")
                return self._get_sample_ktx_data(departure, destination)
            
            print(f"API 응답 items: {items}")
            
            # items가 dict인지 확인하고 item 리스트 추출
            if isinstance(items, dict):
                item_list = items.get('item', [])
            else:
                item_list = items
            
            print(f"파싱할 열차 수: {len(item_list) if isinstance(item_list, list) else '단일 항목'}")      
            if not item_list:
                print("열차 목록이 비어있음, 샘플 데이터 사용")
                return self._get_sample_ktx_data(departure, destination)
            
            # 단일 결과인 경우 리스트로 변환
            if isinstance(item_list, dict):
                item_list = [item_list]
            
            print(f"최종 처리할 열차 수: {len(item_list)}")
            
            trains = []
            for i, item in enumerate(item_list):
                print(f"열차 {i+1} 파싱: {item}")
                # 출발시간 파싱 (YYYYMMDDHHMMSS -> HH:MM)
                dep_time = str(item.get('depplandtime', ''))
                if len(dep_time) >= 12:
                    dep_time = dep_time[8:10] + ':' + dep_time[10:12]
                # 도착시간 파싱 (YYYYMMDDHHMMSS -> HH:MM)
                arr_time = str(item.get('arrplandtime', ''))
                if len(arr_time) >= 12:
                    arr_time = arr_time[8:10] + ':' + arr_time[10:12]
                # 요금 정보
                charge = item.get('adultcharge', '')
                if isinstance(charge, int):
                    charge = f"{charge:,}원"
                elif isinstance(charge, str) and charge.isdigit():
                    charge = f"{int(charge):,}원"
                else:
                    charge = str(charge)
                # 열차번호
                train_no = item.get('trainno', '')
                # 열차종류
                train_type = item.get('traingradename', 'KTX')
                # 출발지/도착지
                dep_name = item.get('depplacename', departure)
                arr_name = item.get('arrplacename', destination)
                train_info = {
                    'type': train_type,
                    'train_no': train_no,
                    'departure_time': dep_time,
                    'arrival_time': arr_time,
                    'price': charge,
                    'departure': dep_name,
                    'arrival': arr_name
                }
                print(f"파싱된 열차 정보: {train_info}")
                trains.append(train_info)
            
            print(f"KTX 조회 성공: {len(trains)}개 열차")
            print(f"모든 열차 정보: {trains}")
            return trains
        except Exception as e:
            print(f"KTX API 조회 오류: {e}")
            return self._get_sample_ktx_data(departure, destination)

 #   def get_srt_info_crawler(self, departure, destination, departure_date):
        """SRT 정보만 크롤러로 조회"""
        try:
            from srt_crawler import get_srt_info_selenium
            results = get_srt_info_selenium(departure, destination, departure_date)
            trains = []
            if results:
                for result in results:
                    trains.append({
                        'type': 'SRT',
                        'train_no': result.get('train_no', ''),
                        'departure_time': result.get('departure_time', ''),
                        'arrival_time': result.get('arrival_time', ''),
                        'price': result.get('price', ''),
                        'available': result.get('available', True),
                        'seat_info': result.get('seat_info', '예약가능')
                    })
            return trains
        except Exception as e:
            print(f"SRT 크롤러 오류: {e}")
            return []

    def _get_sample_ktx_data(self, departure, destination):
        """KTX 샘플 데이터 반환"""
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

    def _get_sample_data(self, departure, destination):
        """크롤링 실패 시 샘플 데이터 반환"""
        base_time_srt = [('08:00', '11:30'), ('09:15', '12:45'), ('10:30', '14:00'), ('12:00', '15:30'), ('14:30', '18:00')]
        base_time_ktx = [('07:30', '11:00'), ('09:00', '12:30'), ('11:00', '14:30'), ('13:00', '16:30'), ('15:30', '19:00')]
        
        sample_trains = []
        
        # SRT 데이터
        for i, (dep_time, arr_time) in enumerate(base_time_srt):
            available = i < 3  # 처음 3개는 예약 가능
            sample_trains.append({
                'type': 'SRT',
                'train_no': f'SRT{301 + i}',
                'departure_time': dep_time,
                'arrival_time': arr_time,
                'price': '50,000원',
                'available': available,
                'seat_info': '예약가능' if available else '매진'
            })
        
        # KTX 데이터
        for i, (dep_time, arr_time) in enumerate(base_time_ktx):
            available = i < 2  # 처음 2개는 예약 가능
            sample_trains.append({
                'type': 'KTX',
                'train_no': f'KTX{101 + i}',
                'departure_time': dep_time,
                'arrival_time': arr_time,
                'price': '55,000원',
                'available': available,
                'seat_info': '예약가능' if available else '매진'
            })
        
        return sample_trains

    def check_express_bus(self, departure, destination, departure_date, arrival_date=None):
        """고속버스 정보 (샘플 데이터)"""
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
        
        return buses

    def get_station_list(self):
        """TAGO API에서 지원하는 역 목록 조회"""
        try:
            # 실제 역 목록 조회 API (서울, 부산, 대전 등 주요 도시)
            stations = {}
            
            # 주요 도시 코드들
            city_codes = {
                11: '서울특별시',
                21: '부산광역시', 
                25: '대전광역시',
                24: '광주광역시',
                22: '대구광역시',
                26: '울산광역시'
            }
            
            for city_code, city_name in city_codes.items():
                base_url = 'http://apis.data.go.kr/1613000/TrainInfoService/getCtyAcctoTrainSttnList'
                params = {
                    'serviceKey': TAGO_API_KEY,
                    'pageNo': 1,
                    'numOfRows': 50,
                    '_type': 'json',
                    'cityCode': city_code
                }
                
                print(f"역 목록 조회: {city_name} (코드: {city_code})")
                
                response = self.session.get(base_url, params=params, timeout=10)
                data = response.json()
                
                if data.get('response', {}).get('header', {}).get('resultCode') == '00':
                    items = data.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                    if items:
                        if isinstance(items, dict):
                            items = [items]
                        stations[city_name] = items
                        print(f"  - {city_name}: {len(items)}개 역 발견")
                    else:
                        print(f"  - {city_name}: 역 없음")
                else:
                    print(f"  - {city_name}: API 오류")
            
            print(f"전체 역 목록: {stations}")
            return stations
            
        except Exception as e:
            print(f"역 목록 조회 오류: {e}")
            return None

    def test_api_connection(self):
        """TAGO API 연결 테스트"""
        try:
            # 간단한 테스트용 요청 (서울-부산, 오늘 날짜)
            from datetime import datetime
            today = datetime.today().strftime('%Y%m%d')
            
            base_url = 'http://apis.data.go.kr/1613000/TrainInfoService/getStrtpntAlocFndTrainInfo'
            params = {
                'serviceKey': TAGO_API_KEY,
                'pageNo': 1,
                'numOfRows': 10,
                '_type': 'json',
                'depPlaceId': 'NAT010000',  # 서울
                'arrPlaceId': 'NAT011680',  # 부산
                'depPlandTime': today
            }
            
            print(f"API 테스트 URL: {base_url}")
            print(f"API 테스트 파라미터: {params}")
            
            response = self.session.get(base_url, params=params, timeout=10)
            print(f"API 테스트 응답 상태: {response.status_code}")
            print(f"API 테스트 응답: {response.text}")
            
            return response.json()
            
        except Exception as e:
            print(f"API 테스트 오류: {e}")
            return None

@app.route('/')
def index():
    favorites = []
    if current_user.is_authenticated:
        favorites = Favorite.query.filter_by(user_id=current_user.id).all()
    # 배경 이미지 폴더 경로
    bg_folder = os.path.join(app.static_folder, 'images', 'backgrounds')
    bg_images = []
    if os.path.exists(bg_folder):
        for f in os.listdir(bg_folder):
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                bg_images.append(f'images/backgrounds/{f}')
    if not bg_images:
        bg_images = []
    # SRT, KTX, 버스 터미널/역 목록 준비 (항상 리스트로)
    srt_stations = sorted(list(SRT_STATION_CODES.keys())) if 'SRT_STATION_CODES' in globals() else []
    ktx_stations = sorted(list(KTX_STATION_CODES.keys())) if 'KTX_STATION_CODES' in globals() else []
    bus_terminals = sorted(list(TERMINAL_NAME_TO_ID.keys())) if 'TERMINAL_NAME_TO_ID' in globals() else []
    return render_template('index.html', favorites=favorites, bg_images=bg_images, srt_stations=srt_stations, ktx_stations=ktx_stations, bus_terminals=bus_terminals)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form.get('confirmPassword', '')

        if not username or not email or not password:
            flash('모든 필드를 입력해주세요.', 'error')
            return render_template('register.html')

        if password != confirm_password:
            flash('비밀번호가 일치하지 않습니다.', 'error')
            return render_template('register.html')

        if User.query.filter_by(username=username).first():
            flash('이미 사용 중인 사용자명입니다.', 'error')
            return render_template('register.html')

        if User.query.filter_by(email=email).first():
            flash('이미 사용 중인 이메일입니다.', 'error')
            return render_template('register.html')

        try:
            user = User(username=username, email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash('회원가입이 완료되었습니다!', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash('회원가입 중 오류가 발생했습니다.', 'error')
            print(f"회원가입 오류: {e}")

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if not username or not password:
            flash('사용자명과 비밀번호를 입력해주세요.', 'error')
            return render_template('login.html')

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            flash('로그인 성공!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('index'))
        else:
            flash('잘못된 사용자명 또는 비밀번호입니다.', 'error')

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
    chat_history = ChatHistory.query.filter_by(user_id=current_user.id).order_by(ChatHistory.timestamp.desc()).limit(50).all()
    favorites = Favorite.query.filter_by(user_id=current_user.id).order_by(Favorite.created_at.desc()).all()

    def safe_str(val):
        if val is None:
            return ''
        try:
            return str(val)
        except Exception:
            return ''

    chat_history_dicts = [
        {
            'id': safe_str(chat.id),
            'message': safe_str(chat.message),
            'response': safe_str(chat.response),
            'timestamp': chat.timestamp.strftime('%Y-%m-%d %H:%M') if chat.timestamp else ''
        }
        for chat in chat_history
    ]
    favorites_dicts = [
        {
            'id': safe_str(fav.id),
            'departure': safe_str(fav.departure),
            'arrival': safe_str(fav.arrival),
            'transport_type': safe_str(fav.transport_type),
            'created_at': fav.created_at.strftime('%Y-%m-%d') if fav.created_at else ''
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

    checker = TransportationChecker()
    result = {'search_info': {
        'departure': departure,
        'destination': destination,
        'departure_date': departure_date,
        'transport_type': transport_type
    }}

    if transport_type in ['ktx', 'ktx_srt']:
        try:
            trains = checker.get_ktx_info_api(departure, destination, dep_date)
            result['ktx'] = trains
            result['ktx_srt'] = trains  # 프론트엔드 호환성을 위해
            print(f"KTX/SRT 검색 결과: {len(trains) if trains else 0}개 열차")
            print(f"전체 응답 구조: {result}")
        except Exception as e:
            print(f"KTX/SRT 검색 오류: {e}")
            return jsonify({'error': f'KTX/SRT 검색 오류: {e}'})
        return jsonify(result)
    elif transport_type == 'bus':
        # 실제 API 기반 버스 조회 (기존 /bus 라우트와 동일하게)
        dep_id = TERMINAL_NAME_TO_ID.get(departure)
        arr_id = TERMINAL_NAME_TO_ID.get(destination)
        if not dep_id or not arr_id:
            return jsonify({'error': '출발지 또는 도착지 터미널명이 올바르지 않습니다.'})
        base_url = 'http://apis.data.go.kr/1613000/ExpBusInfoService/getStrtpntAlocFndExpbusInfo'
        params = {
            'depTerminalId': dep_id,
            'arrTerminalId': arr_id,
            'depPlandTime': bus_date,
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
                return jsonify({'error': f'API 응답이 JSON이 아님: {resp.text[:500]}'})
            items = data.get('response', {}).get('body', {}).get('items', {}).get('item', [])
            buses = []
            if items:
                if isinstance(items, dict):
                    items = [items]
                for item in items:
                    # Format depTime as HH:MM
                    dep_pland_time = item.get('depPlandTime', '')
                    dep_pland_time = str(dep_pland_time)
                    dep_time = ''
                    if len(dep_pland_time) == 12:
                        dep_time = dep_pland_time[8:10] + ':' + dep_pland_time[10:12]
                    # Format arrTime as HH:MM
                    arr_pland_time = item.get('arrPlandTime', '')
                    arr_pland_time = str(arr_pland_time)
                    arr_time = ''
                    if len(arr_pland_time) == 12:
                        arr_time = arr_pland_time[8:10] + ':' + arr_pland_time[10:12]
                    # Format charge as price
                    charge_val = item.get('charge', '')
                    charge_val = str(charge_val)
                    if charge_val and charge_val.isdigit():
                        charge_val = f"{int(charge_val):,}원"
                    buses.append({
                        'departure_time': dep_time,
                        'arrival_time': arr_time,
                        'price': charge_val,
                        'company': item.get('gradeNm', ''),
                        'grade': item.get('gradeNm', ''),
                        'available': True  # Always allow booking for bus
                    })
            result['bus'] = buses
        except Exception as e:
            return jsonify({'error': f'API 오류: {e}'})
        return jsonify(result)
    else:
        return jsonify({'error': '지원하지 않는 교통수단입니다.'})

@app.route('/api/save_favorite', methods=['POST'])
@login_required
def save_favorite():
    try:
        data = request.get_json()
        departure = data.get('departure')
        arrival = data.get('arrival')
        transport_type = data.get('transport_type', '기본')

        if not departure or not arrival:
            return jsonify({'success': False, 'message': '출발지와 도착지를 입력해주세요.'})

        # 중복 체크
        existing = Favorite.query.filter_by(
            user_id=current_user.id,
            departure=departure,
            arrival=arrival,
            transport_type=transport_type
        ).first()

        if existing:
            return jsonify({'success': False, 'message': '이미 즐겨찾기에 추가된 경로입니다.'})

        # 새 즐겨찾기 추가
        favorite = Favorite(
            user_id=current_user.id,
            departure=departure,
            arrival=arrival,
            transport_type=transport_type
        )
        
        db.session.add(favorite)
        db.session.commit()

        return jsonify({'success': True, 'message': '즐겨찾기에 추가되었습니다.'})

    except Exception as e:
        db.session.rollback()
        print(f"즐겨찾기 저장 오류: {e}")
        return jsonify({'success': False, 'message': '즐겨찾기 저장 중 오류가 발생했습니다.'})

@app.route('/api/favorite/<int:favorite_id>', methods=['DELETE'])
@login_required
def delete_favorite(favorite_id):
    try:
        favorite = Favorite.query.filter_by(id=favorite_id, user_id=current_user.id).first()
        
        if not favorite:
            return jsonify({'success': False, 'message': '즐겨찾기를 찾을 수 없습니다.'})

        db.session.delete(favorite)
        db.session.commit()

        return jsonify({'success': True, 'message': '즐겨찾기가 삭제되었습니다.'})

    except Exception as e:
        db.session.rollback()
        print(f"즐겨찾기 삭제 오류: {e}")
        return jsonify({'success': False, 'message': '즐겨찾기 삭제 중 오류가 발생했습니다.'})

@app.route('/api/favorite/<int:favorite_id>', methods=['PUT'])
@login_required
def update_favorite(favorite_id):
    try:
        data = request.get_json()
        departure = data.get('departure')
        arrival = data.get('arrival')
        transport_type = data.get('transport_type')

        favorite = Favorite.query.filter_by(id=favorite_id, user_id=current_user.id).first()
        
        if not favorite:
            return jsonify({'success': False, 'message': '즐겨찾기를 찾을 수 없습니다.'})

        # 중복 체크 (자기 자신 제외)
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

    except Exception as e:
        db.session.rollback()
        print(f"즐겨찾기 수정 오류: {e}")
        return jsonify({'success': False, 'message': '즐겨찾기 수정 중 오류가 발생했습니다.'})

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
        
        checker = TransportationChecker()
        trains = checker.check_ktx_srt(departure, destination, today)
        buses = checker.check_express_bus(departure, destination, today)

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

@app.route('/api/booking/<int:booking_id>')
@login_required
def get_booking_detail(booking_id):
    try:
        booking = Booking.query.filter_by(id=booking_id, user_id=current_user.id).first()
        
        if not booking:
            return jsonify({'success': False, 'message': '예매 정보를 찾을 수 없습니다.'})

        booking_data = {
            'id': booking.id,
            'transport_type': booking.transport_type,
            'departure': booking.departure,
            'arrival': booking.arrival,
            'departure_time': booking.departure_time.strftime('%Y-%m-%d %H:%M'),
            'arrival_time': booking.arrival_time.strftime('%Y-%m-%d %H:%M') if booking.arrival_time else '',
            'price': booking.price,
            'status': booking.status,
            'passenger_name': booking.passenger_name,
            'passenger_phone': booking.passenger_phone,
            'passenger_count': booking.passenger_count,
            'created_at': booking.created_at.strftime('%Y-%m-%d %H:%M')
        }

        return jsonify({'success': True, 'booking': booking_data})

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

        current_user.email = email
        current_user.name = name
        current_user.phone = phone

        db.session.commit()
        flash('프로필이 성공적으로 업데이트되었습니다.', 'success')

    except Exception as e:
        db.session.rollback()
        flash('프로필 업데이트 중 오류가 발생했습니다.', 'error')
        print(f"프로필 업데이트 오류: {e}")

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

        if not current_user.check_password(current_password):
            flash('현재 비밀번호가 올바르지 않습니다.', 'error')
            return redirect(url_for('mypage'))

        if new_password != confirm_password:
            flash('새 비밀번호가 일치하지 않습니다.', 'error')
            return redirect(url_for('mypage'))

        current_user.set_password(new_password)
        db.session.commit()
        flash('비밀번호가 성공적으로 변경되었습니다.', 'success')

    except Exception as e:
        db.session.rollback()
        flash('비밀번호 변경 중 오류가 발생했습니다.', 'error')
        print(f"비밀번호 변경 오류: {e}")

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

@app.route('/api/chatbot', methods=['POST'])
def chatbot_api():
    """Gemini 2.5 Flash 기반 AI 챗봇 API + 실시간 교통편 추천"""
    try:
        data = request.get_json()
        user_message = data.get('message', '').strip()
        print(f"[챗봇] 사용자 메시지: {user_message}")

        if not user_message:
            return jsonify({'success': False, 'response': '메시지를 입력해주세요.'})

        # 여행 경로 추천 키워드가 포함된 경우 실시간 교통편 추천
        if any(kw in user_message for kw in ['여행', '추천', '경로', '교통편']):
            # 아주 단순한 출발지/도착지/날짜 파싱 (실제 서비스는 자연어 파싱 강화 필요)
            import re
            # 예: "서울에서 부산까지 내일 아침에 갈 수 있는 교통편 추천해줘"
            dep, arr, date = None, None, None
            # 출발지/도착지 추출 ("A에서 B까지" 패턴)
            m = re.search(r'([가-힣]+)[에서|발][ ]*([가-힣]+)[까지|행|도착]', user_message)
            if m:
                dep, arr = m.group(1), m.group(2)
            else:
                # "A-B" 패턴
                m2 = re.search(r'([가-힣]+)[-~→\->]+([가-힣]+)', user_message)
                if m2:
                    dep, arr = m2.group(1), m2.group(2)
            # 날짜 추출 ("내일", "오늘", "YYYYMMDD")
            from datetime import datetime, timedelta
            if '내일' in user_message:
                date = (datetime.today() + timedelta(days=1)).strftime('%Y%m%d')
            elif '오늘' in user_message:
                date = datetime.today().strftime('%Y%m%d')
            else:
                m3 = re.search(r'(20\d{6})', user_message)
                if m3:
                    date = m3.group(1)
            if not date:
                date = datetime.today().strftime('%Y%m%d')
            if not dep or not arr:
                # 출발지/도착지 파싱 실패 시 AI로 fallback
                ai_response = generate_gemini_response(current_user if current_user.is_authenticated else None, user_message)
                return jsonify({'success': True, 'response': ai_response})
            # 실시간 교통편 조회
            checker = TransportationChecker()
            trains = checker.check_ktx_srt(dep, arr, date)
            print(f"[챗봇] 열차 조회 결과: {len(trains) if trains else 0}개")
            # 버스 API (실제 API 사용)
            dep_id = TERMINAL_NAME_TO_ID.get(dep)
            arr_id = TERMINAL_NAME_TO_ID.get(arr)
            buses = []
            if dep_id and arr_id:
                base_url = 'http://apis.data.go.kr/1613000/ExpBusInfoService/getStrtpntAlocFndExpbusInfo'
                params = {
                    'depTerminalId': dep_id,
                    'arrTerminalId': arr_id,
                    'depPlandTime': date,
                    'numOfRows': 5,
                    'pageNo': 1,
                    '_type': 'json'
                }
                url = f"{base_url}?serviceKey={API_KEY}"
                try:
                    resp = requests.get(url, params=params, timeout=10)
                    data = resp.json()
                    items = data.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                    if items:
                        if isinstance(items, dict):
                            items = [items]
                        for item in items[:2]:
                            dep_pland_time = str(item.get('depPlandTime', ''))
                            arr_pland_time = str(item.get('arrPlandTime', ''))
                            dep_time = dep_pland_time[8:10] + ':' + dep_pland_time[10:12] if len(dep_pland_time) == 12 else ''
                            arr_time = arr_pland_time[8:10] + ':' + arr_pland_time[10:12] if len(arr_pland_time) == 12 else ''
                            charge_val = str(item.get('charge', ''))
                            if charge_val.isdigit():
                                charge_val = f"{int(charge_val):,}원"
                            buses.append(f"{dep_time}~{arr_time} {item.get('gradeNm','')} {charge_val}")
                except Exception as e:
                    print(f"[챗봇] 버스 API 오류: {e}")
            # 답변 조립
            answer = f"{dep} → {arr} ({date})\n"
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
                chat_record = ChatHistory(
                    user_id=current_user.id,
                    message=user_message,
                    response=ai_response
                )
                db.session.add(chat_record)
                db.session.commit()
            except Exception as e:
                print(f"채팅 기록 저장 오류: {e}")
                db.session.rollback()

        return jsonify({'success': True, 'response': ai_response})

    except Exception as e:
        print(f"[챗봇] 챗봇 API 오류: {e}")
        return jsonify({'success': False, 'response': 'AI 서비스 오류가 발생했습니다.'})

@app.route('/api/chat_history')
@login_required
def get_chat_history():
    """사용자의 채팅 기록 조회"""
    try:
        history = ChatHistory.query.filter_by(user_id=current_user.id)\
                                  .order_by(ChatHistory.timestamp.desc())\
                                  .limit(50)\
                                  .all()
        
        chat_data = []
        for chat in history:
            chat_data.append({
                'message': chat.message,
                'response': chat.response,
                'timestamp': chat.timestamp.strftime('%Y-%m-%d %H:%M')
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
        sample_bookings = [
            {
                'transport_type': 'KTX',
                'departure': '서울',
                'arrival': '부산',
                'departure_time': datetime(2024, 12, 25, 9, 0),
                'arrival_time': datetime(2024, 12, 25, 11, 40),
                'price': '59,800원',
                'passenger_name': current_user.name or current_user.username,
                'passenger_phone': current_user.phone or '010-0000-0000',
                'passenger_count': 1
            },
            {
                'transport_type': 'SRT',
                'departure': '수서',
                'arrival': '대전',
                'departure_time': datetime(2024, 12, 26, 14, 30),
                'arrival_time': datetime(2024, 12, 26, 15, 20),
                'price': '25,400원',
                'passenger_name': current_user.name or current_user.username,
                'passenger_phone': current_user.phone or '010-0000-0000',
                'passenger_count': 2
            },
            {
                'transport_type': '고속버스',
                'departure': '서울',
                'arrival': '광주',
                'departure_time': datetime(2024, 12, 27, 8, 0),
                'arrival_time': datetime(2024, 12, 27, 11, 30),
                'price': '28,000원',
                'passenger_name': current_user.name or current_user.username,
                'passenger_phone': current_user.phone or '010-0000-0000',
                'passenger_count': 1,
                'status': 'cancelled'
            }
        ]
        
        for booking_data in sample_bookings:
            booking = Booking(
                user_id=current_user.id,
                **booking_data
            )
            db.session.add(booking)
        
        db.session.commit()
        return jsonify({'success': True, 'message': '샘플 예매 데이터가 생성되었습니다.'})
        
    except Exception as e:
        db.session.rollback()
        print(f"샘플 데이터 생성 오류: {e}")
        return jsonify({'success': False, 'message': '샘플 데이터 생성 중 오류가 발생했습니다.'})

# 관리자용 데이터베이스 초기화
@app.route('/api/init_db')
def init_database():
    """데이터베이스 테이블 생성"""
    try:
        db.create_all()
        return jsonify({'success': True, 'message': '데이터베이스가 초기화되었습니다.'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'데이터베이스 초기화 오류: {str(e)}'})

# 에러 핸들러
@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
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
with open(os.path.join(os.path.dirname(__file__), '../all_terminal_codes.json'), encoding='utf-8') as f:
    TERMINALS = json.load(f)
    TERMINAL_NAME_TO_ID = {t['터미널명']: t['터미널ID'] for t in TERMINALS}

@app.route('/api/stations')
def get_stations():
    try:
        base_url = 'http://apis.data.go.kr/1613000/TrainInfoService/getCtyAcctoTrainSttnList'
        api_key = TAGO_API_KEY
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
            resp = requests.get(base_url, params=params, timeout=10)
            data = resp.json()
            items = data.get('response', {}).get('body', {}).get('items', {}).get('item', [])
            if isinstance(items, dict):
                items = [items]
            for item in items:
                stations.append({
                    'name': item.get('stationName'),
                    'code': item.get('stationCode')
                })
        # 중복 제거 (역 이름 기준)
        unique_stations = {s['name']: s for s in stations}.values()
        return jsonify({'success': True, 'stations': list(unique_stations)})
    except Exception as e:
        print(f"역 목록 API 오류: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/bus', methods=['GET', 'POST'])
def bus():
    results = []
    error = None
    terminal_names = sorted(TERMINAL_NAME_TO_ID.keys())
    if request.method == 'POST':
        dep = request.form['departure']
        arr = request.form['arrival']
        date = request.form['date'].replace('-', '')  # YYYYMMDD
        dep_id = TERMINAL_NAME_TO_ID.get(dep)
        arr_id = TERMINAL_NAME_TO_ID.get(arr)
        if not dep_id or not arr_id:
            error = '출발지 또는 도착지 터미널명이 올바르지 않습니다.'
        else:
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
        checker = TransportationChecker()
        
        # 1. 역 목록 조회
        print("=== 역 목록 조회 ===")
        station_list = checker.get_station_list()
        
        # 2. API 연결 테스트
        print("=== API 연결 테스트 ===")
        test_result = checker.test_api_connection()
        
        return jsonify({
            'success': True,
            'station_list': station_list,
            'test_result': test_result
        })
        
    except Exception as e:
        print(f"TAGO API 테스트 오류: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)