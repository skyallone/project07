/**
 * AI 여행계획 사이트 메인 JavaScript
 * 공통 기능 및 유틸리티 함수들
 */

// 전역 변수
window.TravelPlannerApp = {
    config: {
        apiBaseUrl: '/api',
        debugMode: false,
        version: '1.0.0'
    },
    utils: {},
    components: {},
    data: {
        user: null,
        favorites: [],
        searchHistory: []
    }
};

// 앱 초기화
document.addEventListener('DOMContentLoaded', function() {
    TravelPlannerApp.init();
});

/**
 * 애플리케이션 초기화
 */
TravelPlannerApp.init = function() {
    console.log('🚄 AI 여행계획 사이트 초기화 중...');
    
    // 공통 이벤트 리스너 설정
    this.setupGlobalEventListeners();
    
    // 유틸리티 초기화
    this.utils.init();
    
    // 컴포넌트 초기화
    this.components.init();
    
    // 사용자 데이터 로드
    this.loadUserData();
    
    // 페이지별 초기화
    this.initPageSpecific();
    
    console.log('✅ 초기화 완료');
};

/**
 * 전역 이벤트 리스너 설정
 */
TravelPlannerApp.setupGlobalEventListeners = function() {
    // ESC 키로 모달 닫기
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            const openModals = document.querySelectorAll('.modal.show');
            openModals.forEach(modal => {
                const bsModal = bootstrap.Modal.getInstance(modal);
                if (bsModal) bsModal.hide();
            });
        }
    });
    
    // 외부 링크에 target="_blank" 추가
    document.querySelectorAll('a[href^="http"]').forEach(link => {
        if (!link.getAttribute('target')) {
            link.setAttribute('target', '_blank');
            link.setAttribute('rel', 'noopener noreferrer');
        }
    });
    
    // 폼 유효성 검사
    document.querySelectorAll('form').forEach(form => {
        form.addEventListener('submit', function(e) {
            if (!form.checkValidity()) {
                e.preventDefault();
                e.stopPropagation();
            }
            form.classList.add('was-validated');
        });
    });
    
    // 네트워크 상태 모니터링
    window.addEventListener('online', () => {
        TravelPlannerApp.utils.showNotification('인터넷 연결이 복구되었습니다.', 'success');
    });
    
    window.addEventListener('offline', () => {
        TravelPlannerApp.utils.showNotification('인터넷 연결이 끊어졌습니다.', 'warning');
    });
};

/**
 * 유틸리티 함수들
 */
TravelPlannerApp.utils = {
    init: function() {
        console.log('🔧 유틸리티 초기화');
    },
    
    /**
     * 알림 메시지 표시
     */
    showNotification: function(message, type = 'info', duration = 5000) {
        // 기존 알림 제거
        const existingToasts = document.querySelectorAll('.toast-notification');
        existingToasts.forEach(toast => toast.remove());
        
        const toast = document.createElement('div');
        toast.className = `alert alert-${this.getAlertClass(type)} alert-dismissible fade show toast-notification`;
        toast.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 9999;
            min-width: 300px;
            max-width: 400px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            border: none;
            border-radius: 8px;
            animation: slideInRight 0.3s ease-out;
        `;
        
        const icon = this.getIcon(type);
        toast.innerHTML = `
            <i class="fas fa-${icon} me-2"></i>${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        document.body.appendChild(toast);
        
        // 자동 제거
        if (duration > 0) {
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.style.animation = 'slideOutRight 0.3s ease-out';
                    setTimeout(() => toast.remove(), 300);
                }
            }, duration);
        }
    },
    
    getAlertClass: function(type) {
        const classes = {
            'success': 'success',
            'error': 'danger',
            'warning': 'warning',
            'info': 'info'
        };
        return classes[type] || 'info';
    },
    
    getIcon: function(type) {
        const icons = {
            'success': 'check-circle',
            'error': 'exclamation-triangle',
            'warning': 'exclamation-circle',
            'info': 'info-circle'
        };
        return icons[type] || 'info-circle';
    },
    
    /**
     * API 호출 헬퍼
     */
    apiCall: function(endpoint, options = {}) {
        const defaultOptions = {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
            },
            cache: 'no-cache'
        };
        
        const config = { ...defaultOptions, ...options };
        
        return fetch(TravelPlannerApp.config.apiBaseUrl + endpoint, config)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .catch(error => {
                console.error('API 호출 오류:', error);
                throw error;
            });
    },
    
    /**
     * 로컬 스토리지 헬퍼
     */
    storage: {
        set: function(key, value) {
            try {
                localStorage.setItem(key, JSON.stringify(value));
                return true;
            } catch (e) {
                console.warn('로컬 스토리지 저장 실패:', e);
                return false;
            }
        },
        
        get: function(key, defaultValue = null) {
            try {
                const item = localStorage.getItem(key);
                return item ? JSON.parse(item) : defaultValue;
            } catch (e) {
                console.warn('로컬 스토리지 읽기 실패:', e);
                return defaultValue;
            }
        },
        
        remove: function(key) {
            try {
                localStorage.removeItem(key);
                return true;
            } catch (e) {
                console.warn('로컬 스토리지 삭제 실패:', e);
                return false;
            }
        }
    },
    
    /**
     * 날짜 포맷터
     */
    formatDate: function(date, format = 'YYYY-MM-DD') {
        if (!(date instanceof Date)) {
            date = new Date(date);
        }
        
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        
        return format
            .replace('YYYY', year)
            .replace('MM', month)
            .replace('DD', day)
            .replace('HH', hours)
            .replace('mm', minutes);
    },
    
    /**
     * 숫자 포맷터 (천 단위 콤마)
     */
    formatNumber: function(number) {
        return number.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    },
    
    /**
     * 디바운스 함수
     */
    debounce: function(func, wait, immediate) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                timeout = null;
                if (!immediate) func(...args);
            };
            const callNow = immediate && !timeout;
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
            if (callNow) func(...args);
        };
    },
    
    /**
     * 스로틀 함수
     */
    throttle: function(func, limit) {
        let inThrottle;
        return function() {
            const args = arguments;
            const context = this;
            if (!inThrottle) {
                func.apply(context, args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        };
    },
    
    /**
     * 폼 데이터를 객체로 변환
     */
    formToObject: function(form) {
        const formData = new FormData(form);
        const object = {};
        formData.forEach((value, key) => {
            object[key] = value;
        });
        return object;
    },
    
    /**
     * URL 파라미터 파싱
     */
    getUrlParams: function() {
        const params = new URLSearchParams(window.location.search);
        const object = {};
        params.forEach((value, key) => {
            object[key] = value;
        });
        return object;
    },
    
    /**
     * 브라우저 지원 확인
     */
    checkBrowserSupport: function() {
        const features = {
            fetch: typeof fetch !== 'undefined',
            localStorage: typeof Storage !== 'undefined',
            flexbox: CSS.supports('display', 'flex'),
            grid: CSS.supports('display', 'grid')
        };
        
        const unsupported = Object.keys(features).filter(key => !features[key]);
        
        if (unsupported.length > 0) {
            console.warn('지원되지 않는 기능:', unsupported);
            this.showNotification(
                '일부 기능이 제한될 수 있습니다. 최신 브라우저를 사용해주세요.',
                'warning'
            );
        }
        
        return features;
    }
};

/**
 * UI 컴포넌트들
 */
TravelPlannerApp.components = {
    init: function() {
        console.log('🎨 컴포넌트 초기화');
        this.initTooltips();
        this.initPopovers();
        this.initScrollToTop();
        this.initLazyLoading();
    },
    
    /**
     * 툴팁 초기화
     */
    initTooltips: function() {
        const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltipTriggerList.map(function(tooltipTriggerEl) {
            return new bootstrap.Tooltip(tooltipTriggerEl);
        });
    },
    
    /**
     * 팝오버 초기화
     */
    initPopovers: function() {
        const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
        popoverTriggerList.map(function(popoverTriggerEl) {
            return new bootstrap.Popover(popoverTriggerEl);
        });
    },
    
    /**
     * 스크롤 투 탑 버튼
     */
    initScrollToTop: function() {
        const scrollBtn = document.createElement('button');
        scrollBtn.className = 'btn btn-primary scroll-to-top';
        scrollBtn.innerHTML = '<i class="fas fa-arrow-up"></i>';
        scrollBtn.style.cssText = `
            position: fixed;
            bottom: 20px;
            right: 20px;
            width: 50px;
            height: 50px;
            border-radius: 50%;
            display: none;
            z-index: 1000;
            transition: all 0.3s ease;
        `;
        
        document.body.appendChild(scrollBtn);
        
        // 스크롤 이벤트
        window.addEventListener('scroll', TravelPlannerApp.utils.throttle(() => {
            if (window.pageYOffset > 300) {
                scrollBtn.style.display = 'block';
            } else {
                scrollBtn.style.display = 'none';
            }
        }, 100));
        
        // 클릭 이벤트
        scrollBtn.addEventListener('click', () => {
            window.scrollTo({
                top: 0,
                behavior: 'smooth'
            });
        });
    },
    
    /**
     * 레이지 로딩
     */
    initLazyLoading: function() {
        if ('IntersectionObserver' in window) {
            const lazyImages = document.querySelectorAll('img[data-src]');
            const imageObserver = new IntersectionObserver((entries, observer) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        const img = entry.target;
                        img.src = img.dataset.src;
                        img.classList.remove('lazy');
                        imageObserver.unobserve(img);
                    }
                });
            });
            
            lazyImages.forEach(img => imageObserver.observe(img));
        }
    },
    
    /**
     * 로딩 스피너 표시/숨김
     */
    showLoading: function(element) {
        const spinner = document.createElement('div');
        spinner.className = 'loading-overlay';
        spinner.innerHTML = `
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">Loading...</span>
            </div>
        `;
        spinner.style.cssText = `
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(255, 255, 255, 0.8);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 1000;
        `;
        
        element.style.position = 'relative';
        element.appendChild(spinner);
    },
    
    hideLoading: function(element) {
        const spinner = element.querySelector('.loading-overlay');
        if (spinner) {
            spinner.remove();
        }
    }
};

/**
 * 사용자 데이터 관리
 */
TravelPlannerApp.loadUserData = function() {
    // 즐겨찾기 데이터 로드
    this.data.favorites = this.utils.storage.get('favorites', []);
    
    // 검색 기록 로드
    this.data.searchHistory = this.utils.storage.get('searchHistory', []);
    
    console.log('📊 사용자 데이터 로드 완료');
};

/**
 * 페이지별 초기화
 */
TravelPlannerApp.initPageSpecific = function() {
    const path = window.location.pathname;
    
    switch(path) {
        case '/':
            this.initIndexPage();
            break;
        case '/chatbot':
            this.initChatbotPage();
            break;
        case '/mypage':
            this.initMyPage();
            break;
        default:
            console.log('기본 페이지 초기화');
    }
};

/**
 * 메인 페이지 초기화
 */
TravelPlannerApp.initIndexPage = function() {
    console.log('🏠 메인 페이지 초기화');
    
    // 오늘 날짜를 기본값으로 설정
    const today = new Date().toISOString().split('T')[0];
    const departureDateInput = document.getElementById('departure_date');
    if (departureDateInput && !departureDateInput.value) {
        departureDateInput.value = today;
    }
};

/**
 * 챗봇 페이지 초기화
 */
TravelPlannerApp.initChatbotPage = function() {
    console.log('🤖 챗봇 페이지 초기화');
    
    // 채팅 기록 로드
    this.loadChatHistory();
};

/**
 * 마이페이지 초기화
 */
TravelPlannerApp.initMyPage = function() {
    console.log('👤 마이페이지 초기화');
    
    // 사용자 설정 로드
    this.loadUserSettings();
};

/**
 * 채팅 기록 로드
 */
TravelPlannerApp.loadChatHistory = function() {
    // 로그인한 사용자의 채팅 기록 로드 로직
    console.log('💬 채팅 기록 로드');
};

/**
 * 사용자 설정 로드
 */
TravelPlannerApp.loadUserSettings = function() {
    // 사용자 설정 로드 로직
    console.log('⚙️ 사용자 설정 로드');
};

// CSS 애니메이션 추가
const style = document.createElement('style');
style.textContent = `
    @keyframes slideInRight {
        from {
            opacity: 0;
            transform: translateX(100%);
        }
        to {
            opacity: 1;
            transform: translateX(0);
        }
    }
    
    @keyframes slideOutRight {
        from {
            opacity: 1;
            transform: translateX(0);
        }
        to {
            opacity: 0;
            transform: translateX(100%);
        }
    }
    
    .scroll-to-top:hover {
        transform: translateY(-3px);
        box-shadow: 0 6px 20px rgba(0, 123, 255, 0.3);
    }
    
    .lazy {
        opacity: 0;
        transition: opacity 0.3s;
    }
    
    .lazy.loaded {
        opacity: 1;
    }
`;
document.head.appendChild(style);

// 전역 함수로 내보내기 (하위 호환성)
window.showNotification = TravelPlannerApp.utils.showNotification.bind(TravelPlannerApp.utils);
window.apiCall = TravelPlannerApp.utils.apiCall.bind(TravelPlannerApp.utils);

console.log('📜 main.js 로드 완료');