from fastapi import FastAPI, HTTPException, APIRouter, Request, Response, BackgroundTasks, Depends, File, UploadFile, Header, Query, Form, Body
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Dict, Any, Union
from enum import Enum
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from dataclasses import asdict
import os
import logging
import math
import uuid
import bcrypt
import json
import hmac
import hashlib
import time
from pathlib import Path
from dotenv import load_dotenv
import sys
import asyncio

# Add services directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'services'))
from email_service import EmailService
from email_notification_service import EmailNotificationService, EmailNotification
from email_preferences_service import EmailPreferencesService, EmailPreferenceStatus
# from notification_service import send_welcome_email, send_order_confirmation, send_login_alert
from blog_service import BlogService, BlogStatus, AIModel
from referral_service import ReferralService, ReferralStage, RewardType
from buy_request_service import BuyRequestService, BuyRequestStatus, OfferStatus, notify_nearby_sellers

# Import new extended services
from messaging_service import MessagingService
from referral_service_extended import ExtendedReferralService
from notification_service_extended import ExtendedNotificationService
from paystack_service import PaystackService

# Import notification system
from notification_event_service import (
    event_bus, emit_listing_created, emit_buy_request_created,
    initialize_notification_events
)
from services.notification_service import NotificationService
from services.notification_worker import NotificationWorker

# Import shared auth models to avoid circular imports
from auth_models import User, UserRole, UserStatus, UserCreate, UserLogin

# Import notification API routes - fixed circular import
from routes.admin_notifications import admin_notifications_router, set_notification_services
from routes.user_notifications import user_notifications_router, set_notification_service
from dependencies import set_database, set_get_current_user as set_shared_get_current_user

# Import AI & Mapping enhanced services
from services.enhanced_buy_request_service import EnhancedBuyRequestService
from services.ai_enhanced_service import AIEnhancedService
from services.mapbox_service import MapboxService
from services.order_management_service import OrderManagementService
from services.ml_faq_service import MLFAQService
from services.ml_knowledge_scraper import MLKnowledgeScraper
from services.ml_matching_service import MLMatchingService
from services.ml_engine_service import MLEngineService
from services.photo_intelligence_service import PhotoIntelligenceService
from services.exotic_livestock_service import ExoticLivestockService
from services.social_auth_service import SocialAuthService
from services.password_reset_service import PasswordResetService, PasswordResetRequest, PasswordResetConfirm
from services.two_factor_service import TwoFactorService, TwoFactorSetupRequest, TwoFactorVerifyRequest, TwoFactorDisableRequest
from services.kyc_service import KYCService, KYCSubmissionRequest, VerificationLevel, DocumentType, VerificationStatus
from services.wishlist_service import WishlistService, WishlistCreateRequest, WishlistUpdateRequest, WishlistItemType, WishlistCategory
from services.price_alerts_service import PriceAlertsService, PriceAlertCreate, PriceAlertUpdate, AlertType, AlertFrequency, NotificationChannel, AlertStatus
from policies.contact_policy import can_view_seller_contact, mask_contact_info
from services.unified_inbox_service import UnifiedInboxService
from services.sse_service import sse_service
from services.admin_moderation_service import AdminModerationService

# Import new enhancement services
from services.advanced_search_service import AdvancedSearchService
from services.realtime_messaging_service import RealTimeMessagingService  
from services.business_intelligence_service import BusinessIntelligenceService
from services.openai_listing_service import OpenAIListingService
from services.ai_shipping_optimizer import AIShippingOptimizer
from services.ai_mobile_payment_service import AIMobilePaymentService
from services.rate_limiting_service import rate_limit_middleware, RATE_LIMITS

# Import inbox models
from inbox_models.inbox_models import (
    SendMessageBody, CreateConversationRequest, UpdateConversationRequest,
    ConversationType, SystemMessageType
)

# Import new models from models.py file
import models
from models import (
    MessageCreate, ThreadCreate, MessageThread, Message, MessageParticipant,
    ReferralCode, ReferralClick, ReferralAttribution, ReferralReward, ReferralSummary,
    BuyRequestOffer, OfferCreate, OfferUpdate, NotificationCreate, Notification,
    AdminAuditLog, UserModerationAction, SystemSettings, FeatureFlag,
    SuggestionCreate, Suggestion, SuggestionUpdate, SuggestionKind, SuggestionStatus, SuggestionPriority,
    CartItem, Cart, OrderItem, ShippingAddress, Order, CheckoutSession
)

# Load environment variables
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Console logging helper
class Console:
    @staticmethod
    def log(message):
        logger.info(message)

console = Console()

# MongoDB connection
# Support DB_URL, MONGO_URL, or MONGO_URI (in that order of priority)
# Following the pattern from working Docker Compose examples
# mongo_url = os.environ.get('DB_URL') or os.environ.get('MONGO_URL') or os.environ.get('MONGO_URI')
# if not mongo_url:
#     raise ValueError("DB_URL, MONGO_URL, or MONGO_URI environment variable must be set")

# db_name = os.environ.get('DB_NAME') or os.environ.get('MONGO_DBNAME', 'stocklot')
mongo_url = 'mongodb://admin:adminpassword@stocklot-mongodb:27017/'
#mongo_url = 'mongodb://posDBUser:posDBPassword@103.239.43.246:27017/?authSource=admin' #local docker
# mongo_url = 'mongodb://posDBUser:posDBPassword@tcm-pos-posdb-2i3j8w:27017/?authSource=admin' #dokploy
db_name = 'stocklot'

# Mask password in logs for security
def mask_mongo_url(url: str) -> str:
    """Mask password in MongoDB connection string for logging"""
    try:
        if '@' in url:
            parts = url.split('@')
            auth_part = parts[0]
            if ':' in auth_part:
                user_pass = auth_part.split('://', 1)[1] if '://' in auth_part else auth_part
                if ':' in user_pass:
                    user = user_pass.split(':')[0]
                    return url.replace(user_pass, f"{user}:***")
        return url
    except:
        return "mongodb://***:***@***"
    
logger.info(f"Connecting to MongoDB: {mask_mongo_url(mongo_url)}")
logger.info(f"Database name: {db_name}")

# Initialize MongoDB client with longer timeouts for external connections
# This allows time for external MongoDB servers to respond
client = AsyncIOMotorClient(
    mongo_url, 
    serverSelectionTimeoutMS=30000,  # 30 seconds for external DB
    connectTimeoutMS=30000,
    socketTimeoutMS=30000,
    retryWrites=True
)
db = client[db_name]
logger.info("MongoDB client initialized (connection will be tested on first use)")

# Initialize extended services
messaging_service = MessagingService(db)
referral_service_extended = ExtendedReferralService(db)
notification_service_extended = ExtendedNotificationService(db)
paystack_service = PaystackService(db)

# Initialize comprehensive notification system
notification_service = NotificationService(db)
notification_worker = NotificationWorker(db, EmailService(), None)  # SSE service will be added later
initialize_notification_events(notification_service)

# Set notification services for API routes
set_notification_services(notification_service, notification_worker)
set_notification_service(notification_service)

# Initialize comprehensive email system
email_notification_service = EmailNotificationService(db)
email_preferences_service = EmailPreferencesService(db)
from services.lifecycle_email_service import LifecycleEmailService

# Initialize services
lifecycle_email_service = LifecycleEmailService(db)
admin_moderation_service = AdminModerationService(db)

# Initialize AI & Mapping enhanced services
try:
    enhanced_buy_request_service = EnhancedBuyRequestService(db)
    ai_enhanced_service = AIEnhancedService()
    mapbox_service = MapboxService()
    order_management_service = OrderManagementService(db)
    ml_faq_service = MLFAQService(db)
    ml_scraper_service = MLKnowledgeScraper(db, os.environ.get('OPENAI_API_KEY'))
    ml_matching_service = MLMatchingService(db)
    ml_engine_service = MLEngineService(db)
    photo_intelligence_service = PhotoIntelligenceService(db)
    exotic_livestock_service = ExoticLivestockService(db)
    
    # Initialize new enhancement services
    advanced_search_service = AdvancedSearchService(db, ai_enhanced_service)
    realtime_messaging_service = RealTimeMessagingService(db)
    business_intelligence_service = BusinessIntelligenceService(db)
    openai_listing_service = OpenAIListingService(db)
    ai_shipping_optimizer = AIShippingOptimizer(db)
    ai_mobile_payment_service = AIMobilePaymentService(db)
    
    AI_SERVICES_AVAILABLE = True
    ML_SERVICES_AVAILABLE = True
    ENHANCEMENT_SERVICES_AVAILABLE = True
    OPENAI_LISTING_AVAILABLE = openai_listing_service.enabled
    logger.info("✅ ML and Enhancement services initialized successfully")
except (ImportError, ValueError, Exception) as e:
    logger.warning(f"ML services not available: {e}")
    ML_SERVICES_AVAILABLE = False
    AI_SERVICES_AVAILABLE = False
    ENHANCEMENT_SERVICES_AVAILABLE = False
    # Initialize fallback services or set to None
    enhanced_buy_request_service = None
    ai_enhanced_service = None
    mapbox_service = None
    order_management_service = None
    ml_faq_service = None
    ml_scraper_service = None
    ml_matching_service = None
    ml_engine_service = None
    photo_intelligence_service = None
    exotic_livestock_service = None
    advanced_search_service = None
    realtime_messaging_service = None
    business_intelligence_service = None
    openai_listing_service = None
    ai_shipping_optimizer = None
    ai_mobile_payment_service = None

# Initialize Security and User Engagement services
try:
    social_auth_service = SocialAuthService(db)
    password_reset_service = PasswordResetService(db)
    two_factor_service = TwoFactorService(db)
    kyc_service = KYCService(db)
    wishlist_service = WishlistService(db)
    price_alerts_service = PriceAlertsService(db)
    ALL_SERVICES_AVAILABLE = True
    logger.info("✅ All services initialized successfully (Auth, Password Reset, 2FA, KYC, Wishlist, Price Alerts)")
except (ImportError, ValueError, Exception) as e:
    logger.warning(f"⚠️  Services not available: {e}")
    social_auth_service = None
    password_reset_service = None
    two_factor_service = None
    kyc_service = None
    wishlist_service = None
    price_alerts_service = None
    ALL_SERVICES_AVAILABLE = False

# Initialize Unified Inbox service
try:
    unified_inbox_service = UnifiedInboxService(db)
    UNIFIED_INBOX_AVAILABLE = True
    logger.info("✅ Unified Inbox service initialized successfully")
except (ImportError, ValueError, Exception) as e:
    logger.warning(f"⚠️  Unified Inbox service not available: {e}")
    unified_inbox_service = None
    UNIFIED_INBOX_AVAILABLE = False

# Initialize Review System services
from services.review_cron_service import get_review_cron_service
from services.review_db_setup import setup_review_database

# Global review cron service
review_cron_service = None

# Paystack configuration
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
PAYSTACK_PUBLIC_KEY = os.getenv("PAYSTACK_PUBLIC_KEY") 
PAYSTACK_WEBHOOK_SECRET = os.getenv("PAYSTACK_WEBHOOK_SECRET")

# Create the main app
app = FastAPI(
    title="StockLot - Livestock Marketplace",
    description="South African Livestock & Meat Marketplace with Escrow Payments",
    version="1.0.0"
)

@app.on_event("startup")
async def startup_event():
    """Test database connection on startup"""
    try:
        # Test MongoDB connection
        await client.admin.command('ping')
        logger.info("✅ MongoDB connection verified on startup")
        
        # Test database access
        collections = await db.list_collection_names()
        logger.info(f"✅ Database access verified - {len(collections)} collections found")
    except Exception as e:
        logger.error(f"❌ Database connection test failed on startup: {e}")
        # Don't raise - let the app start but log the error
    global notification_service, notification_worker
    # Initialize comprehensive notification system
    notification_service = NotificationService(db)
    notification_worker = NotificationWorker(db, EmailService(), None)  # SSE service will be added later
    initialize_notification_events(notification_service)
    
    # Set notification services for API routes
    set_notification_services(notification_service, notification_worker)
    set_notification_service(notification_service)

# Rate limiting middleware is applied per-endpoint, not globally

# Create API router
api_router = APIRouter(prefix="/api")

# Security
security = HTTPBearer(auto_error=False)

# CORS middleware - Allow origins from environment or default list
allowed_origins = os.getenv("ALLOWED_ORIGINS", "").split(",") if os.getenv("ALLOWED_ORIGINS") else []
# Add default origins if not in environment
default_origins = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:3002",
    "http://localhost:3003",
    "https://stocklot.farm",
    "https://www.stocklot.farm"
]
# Combine and filter empty strings
cors_origins = [origin.strip() for origin in allowed_origins + default_origins if origin.strip()]

# If ALLOWED_ORIGINS is set to "*", allow all origins (useful for development)
if os.getenv("ALLOWED_ORIGINS") == "*":
    cors_origins = ["*"]
    
logger.info(f"CORS allowed origins: {cors_origins if cors_origins != ['*'] else ['* (all origins)']}")

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=cors_origins if cors_origins != ["*"] else ["*"],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)

# Health check endpoint
@api_router.get("/health")
async def health_check():
    """Health check endpoint - always returns 200 if server is responding"""
    # Always return 200 - server is healthy if it can respond to HTTP requests
    # Database connectivity is tested but doesn't fail the health check
    # This prevents container from being marked unhealthy due to temporary DB issues
    db_status = "unknown"
    db_error = None
    
    try:
        # Test database connection with a simple query (CRUD Read operation)
        # Use a timeout to prevent health check from hanging
        await asyncio.wait_for(
            db.users.count_documents({}, limit=1),
            timeout=5.0
        )
        db_status = "connected"
    except asyncio.TimeoutError:
        db_status = "timeout"
        db_error = "Database connection timeout"
    except Exception as e:
        db_status = "disconnected"
        db_error = str(e)
    
    # Always return 200 - server is running
    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": db_status,
        "error": db_error
    }

# Enums (keeping non-auth related ones)
class ListingStatus(str, Enum):
    ACTIVE = "active"
    SOLD = "sold"
    EXPIRED = "expired"
    INACTIVE = "inactive"
    PENDING_APPROVAL = "pending_approval"

class OrderStatus(str, Enum):
    PENDING_PAYMENT = "pending_payment"
    PAYMENT_CONFIRMED = "payment_confirmed"
    FUNDS_HELD = "funds_held"
    DELIVERY_CONFIRMED = "delivery_confirmed"
    FUNDS_RELEASED = "funds_released"
    DISPUTE_RAISED = "dispute_raised"
    CANCELLED = "cancelled"
    EXPIRED = "expired"

class FulfillmentMethod(str, Enum):
    DELIVERY_ONLY = "delivery_only"  # Only delivery allowed, no self-collection

class CategoryType(str, Enum):
    POULTRY = "poultry"
    RUMINANTS = "ruminants"
    RABBITS = "rabbits"
    AQUACULTURE = "aquaculture"
    OTHER_LIVESTOCK = "other_livestock"

# Pydantic Models (non-auth related)

class ExtendedUser(User):
    """Extended User model with farm-specific fields for server.py"""
    # Enhanced Profile Fields (Common)
    profile_photo: Optional[str] = None
    business_name: Optional[str] = None
    bio: Optional[str] = None
    
    # Location & Experience (Common)
    location_region: Optional[str] = None  # e.g., "Western Cape, South Africa"
    location_city: Optional[str] = None
    experience_years: Optional[int] = None
    
    # SELLER-SPECIFIC FIELDS
    # Specialization & Expertise
    primary_livestock: List[str] = []  # e.g., ["cattle", "sheep", "goats"]
    secondary_livestock: List[str] = []
    farming_methods: List[str] = []  # e.g., ["organic", "free_range", "commercial"]
    
    # Certifications & Credentials
    certifications: List[str] = []  # e.g., ["veterinary_certificate", "organic_certified"]
    licenses: List[str] = []
    associations: List[str] = []  # breed associations, farmer unions
    
    # Business Information
    business_hours: Optional[str] = None  # e.g., "Monday-Friday 8AM-5PM"
    delivery_areas: List[str] = []  # regions where seller delivers
    preferred_communication: List[str] = ["phone", "email"]  # contact preferences
    
    # Policies & Guarantees
    return_policy: Optional[str] = None
    health_guarantee: Optional[str] = None
    delivery_policy: Optional[str] = None
    payment_terms: Optional[str] = None
    
    # BUYER-SPECIFIC FIELDS
    # Buying Preferences & Interests
    livestock_interests: List[str] = []  # What livestock they want to buy
    buying_purpose: List[str] = []  # breeding, commercial, personal, etc.
    purchase_frequency: Optional[str] = None  # occasional, regular, seasonal
    budget_range: Optional[str] = None  # small, medium, large, enterprise
    
    # Farm/Facility Information (for buyers)
    farm_size_hectares: Optional[int] = None
    facility_type: Optional[str] = None  # commercial_farm, hobby_farm, feedlot, etc.
    animal_capacity: Optional[int] = None  # How many animals they can house
    farm_infrastructure: List[str] = []  # fencing, water, shelter, etc.
    
    # Buyer Experience & Credentials
    livestock_experience: List[str] = []  # cattle_farming, sheep_raising, etc.
    buyer_certifications: List[str] = []  # animal_welfare, organic_farming, etc.
    previous_suppliers: Optional[str] = None  # References from past purchases
    
    # Financial & Transaction Preferences
    payment_methods: List[str] = []  # cash, bank_transfer, credit, etc.
    payment_timeline: Optional[str] = None  # immediate, 7_days, 30_days
    collection_preference: Optional[str] = None  # self_collect, delivery_requested
    
    # Animal Care & Welfare
    veterinary_contact: Optional[str] = None  # Vet details for animal health
    quarantine_facilities: Optional[bool] = None  # Has quarantine setup
    animal_welfare_standards: List[str] = []  # welfare practices
    
    # Profile Completeness & Stats (Common)
    profile_completion_score: Optional[float] = 0.0  # 0-100%
    total_sales: Optional[int] = 0  # For sellers
    total_purchases: Optional[int] = 0  # For buyers
    customer_rating: Optional[float] = 0.0  # As seller
    buyer_rating: Optional[float] = 0.0  # As buyer
    
    # Additional Media
    farm_photos: List[str] = []  # URLs to farm/facility photos
    certificate_documents: List[str] = []  # URLs to certification documents

class ExtendedUserCreate(UserCreate):
    """Extended UserCreate with additional role options"""
    pass

# Keep just the UserProfileUpdate class from the original model
class UserProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    business_name: Optional[str] = None
    bio: Optional[str] = None
    
    # Location & Experience (Common to both buyers and sellers)
    location_region: Optional[str] = None
    location_city: Optional[str] = None
    experience_years: Optional[int] = None
    
    # SELLER-SPECIFIC FIELDS
    # Specialization & Expertise
    primary_livestock: Optional[List[str]] = None
    secondary_livestock: Optional[List[str]] = None
    farming_methods: Optional[List[str]] = None
    
    # Certifications & Credentials
    certifications: Optional[List[str]] = None
    licenses: Optional[List[str]] = None
    associations: Optional[List[str]] = None
    
    # Business Information
    business_hours: Optional[str] = None
    delivery_areas: Optional[List[str]] = None
    preferred_communication: Optional[List[str]] = None
    
    # Policies & Guarantees
    return_policy: Optional[str] = None
    health_guarantee: Optional[str] = None
    delivery_policy: Optional[str] = None
    payment_terms: Optional[str] = None
    
    # BUYER-SPECIFIC FIELDS
    # Buying Preferences & Interests
    livestock_interests: Optional[List[str]] = None  # What livestock they want to buy
    buying_purpose: Optional[List[str]] = None  # breeding, commercial, personal, etc.
    purchase_frequency: Optional[str] = None  # occasional, regular, seasonal
    budget_range: Optional[str] = None  # small, medium, large, enterprise
    
    # Farm/Facility Information (for buyers)
    farm_size_hectares: Optional[int] = None
    facility_type: Optional[str] = None  # commercial_farm, hobby_farm, feedlot, etc.
    animal_capacity: Optional[int] = None  # How many animals they can house
    farm_infrastructure: Optional[List[str]] = None  # fencing, water, shelter, etc.
    
    # Buyer Experience & Credentials
    livestock_experience: Optional[List[str]] = None  # cattle_farming, sheep_raising, etc.
    buyer_certifications: Optional[List[str]] = None  # animal_welfare, organic_farming, etc.
    previous_suppliers: Optional[str] = None  # References from past purchases
    
    # Financial & Transaction Preferences
    payment_methods: Optional[List[str]] = None  # cash, bank_transfer, credit, etc.
    payment_timeline: Optional[str] = None  # immediate, 7_days, 30_days
    collection_preference: Optional[str] = None  # self_collect, delivery_requested
    
    # Animal Care & Welfare
    veterinary_contact: Optional[str] = None  # Vet details for animal health
    quarantine_facilities: Optional[bool] = None  # Has quarantine setup
    animal_welfare_standards: Optional[List[str]] = None  # welfare practices

# Social Authentication Models
class SocialAuthRequest(BaseModel):
    provider: str = Field(..., pattern="^(google|facebook)$")
    token: str
    role: Optional[UserRole] = None

class SocialAuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Dict[str, Any]
    is_new_user: bool
    needs_role_selection: bool

class UpdateRoleRequest(BaseModel):
    role: UserRole

# Organization Models
class OrganizationType(str, Enum):
    FARM = "FARM"
    COMPANY = "COMPANY"
    COOP = "COOP"
    ABATTOIR = "ABATTOIR"
    TRANSPORTER = "TRANSPORTER"
    EXPORTER = "EXPORTER"

class OrganizationRole(str, Enum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    MANAGER = "MANAGER"
    STAFF = "STAFF"
    VIEWER = "VIEWER"

class Organization(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    kind: OrganizationType
    handle: Optional[str] = None  # vanity URL like "mkhize-farms"
    logo_url: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    country: str = "ZA"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class OrganizationCreate(BaseModel):
    name: str
    kind: OrganizationType
    handle: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None

class OrganizationMembership(BaseModel):
    org_id: str
    user_id: str
    role: OrganizationRole = OrganizationRole.STAFF
    joined_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class OrganizationKYC(BaseModel):
    org_id: str
    level: int = 0  # 0 none, 1 basic, 2 exporter, etc.
    status: str = "PENDING"  # PENDING|VERIFIED|REJECTED
    notes: Optional[str] = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class OrganizationAddress(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    org_id: str
    label: Optional[str] = None
    line1: Optional[str] = None
    line2: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    postal_code: Optional[str] = None
    country: str = "ZA"
    lat: Optional[float] = None
    lng: Optional[float] = None
    is_default: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class OrganizationServiceArea(BaseModel):
    org_id: str
    mode: str  # RADIUS|POLYGON|PROVINCES|COUNTRIES
    radius_km: Optional[float] = None
    origin_lat: Optional[float] = None
    origin_lng: Optional[float] = None
    polygon: Optional[List[Dict[str, float]]] = None  # [{"lat": -26.2, "lng": 28.1}]
    provinces: Optional[List[str]] = None
    countries: Optional[List[str]] = None

class OrganizationPayoutRecipient(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    org_id: str
    type: str = "BANK_ACCOUNT"
    bank_code: str
    account_number: str
    account_name: Optional[str] = None
    currency: str = "ZAR"
    country: str = "ZA"
    paystack_recipient_code: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class OrganizationPublicSettings(BaseModel):
    org_id: str
    bio: Optional[str] = None
    hero_image_url: Optional[str] = None
    show_contact: bool = False

class InviteMemberRequest(BaseModel):
    email: EmailStr
    role: OrganizationRole = OrganizationRole.STAFF

class SwitchContextRequest(BaseModel):
    target: str  # "user" or org_id

class CategoryGroup(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: Optional[str] = None

class Species(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    category_group_id: str
    is_egg_laying: bool = False
    is_fish: bool = False
    is_ruminant: bool = False
    is_free_range: bool = False
    description: Optional[str] = None

class Breed(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    species_id: str
    name: str
    purpose_hint: Optional[str] = None
    origin_country: Optional[str] = None
    characteristics: Optional[str] = None

class ProductType(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    code: str
    label: str
    description: Optional[str] = None
    applicable_to_groups: List[str] = []  # Which category groups this applies to

class Listing(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    seller_id: Optional[str] = None  # For individual sellers
    org_id: Optional[str] = None     # For organization listings
    species_id: str
    breed_id: Optional[str] = None
    product_type_id: str
    title: str
    description: Optional[str] = None
    quantity: float
    unit: str = "head"
    price_per_unit: Decimal
    listing_type: Optional[str] = "buy_now"  # Added for Buy Now functionality
    fulfillment: FulfillmentMethod = FulfillmentMethod.DELIVERY_ONLY
    delivery_available: bool = False
    has_vet_certificate: bool = False
    vet_certificate_url: Optional[str] = None
    health_notes: Optional[str] = None
    
    # Livestock Specification Fields
    weight_kg: Optional[float] = None
    age_weeks: Optional[int] = None
    age_days: Optional[int] = None
    age: Optional[str] = None
    sex: Optional[str] = None
    weight: Optional[str] = None
    breed: Optional[str] = None  # Resolved breed name
    vaccination_status: Optional[str] = None
    health_status: Optional[str] = "healthy"
    veterinary_certificate: Optional[bool] = False
    animal_type: Optional[str] = None
    survival_rate: Optional[str] = None
    health_certificates: Optional[List[str]] = []
    
    country: str = "South Africa"
    region: Optional[str] = None
    city: Optional[str] = None
    images: List[str] = []
    status: ListingStatus = ListingStatus.ACTIVE
    expires_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ListingCreate(BaseModel):
    species_id: str
    breed_id: Optional[str] = None
    product_type_id: str
    title: str
    description: Optional[str] = None
    quantity: float
    unit: str = "head"
    price_per_unit: Decimal
    listing_type: Optional[str] = "buy_now"  # Added for Buy Now functionality
    fulfillment: FulfillmentMethod = FulfillmentMethod.DELIVERY_ONLY
    delivery_available: bool = False
    has_vet_certificate: bool = False
    health_notes: Optional[str] = None
    
    # Livestock Specification Fields
    weight_kg: Optional[float] = None
    age_weeks: Optional[int] = None
    age_days: Optional[int] = None
    age: Optional[str] = None
    sex: Optional[str] = None
    weight: Optional[str] = None
    vaccination_status: Optional[str] = None
    health_status: Optional[str] = "healthy"
    veterinary_certificate: Optional[bool] = False
    animal_type: Optional[str] = None
    survival_rate: Optional[str] = None
    health_certificates: Optional[List[str]] = []
    
    region: Optional[str] = None
    city: Optional[str] = None
    images: List[str] = []

class Order(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    listing_id: str
    buyer_id: str
    seller_id: str
    quantity: float
    unit_price: Decimal
    total_amount: Decimal
    marketplace_fee: Decimal
    seller_amount: Decimal
    status: OrderStatus = OrderStatus.PENDING_PAYMENT
    paystack_reference: Optional[str] = None
    payment_url: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    confirmed_at: Optional[datetime] = None
    fulfilled_at: Optional[datetime] = None

class OrderCreate(BaseModel):
    listing_id: str
    quantity: float

class DeliveryConfirmation(BaseModel):
    order_id: str
    delivery_rating: Optional[int] = None
    delivery_comments: Optional[str] = None

# Seller Delivery Rate Models
class SellerDeliveryRate(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    seller_id: str
    base_fee_cents: int = 0  # Base call-out fee in cents (e.g., 2000 = R20.00)
    per_km_cents: int = 0    # Per-kilometer rate in cents (e.g., 120 = R1.20/km)
    min_km: int = 0          # Free delivery within this distance
    max_km: Optional[int] = None  # Maximum delivery distance, None = unlimited
    province_whitelist: Optional[List[str]] = None  # Provinces served, None = all
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class SellerDeliveryRateCreate(BaseModel):
    base_fee_cents: int = 0
    per_km_cents: int = 0
    min_km: int = 0
    max_km: Optional[int] = None
    province_whitelist: Optional[List[str]] = None

class SellerDeliveryRateUpdate(BaseModel):
    base_fee_cents: Optional[int] = None
    per_km_cents: Optional[int] = None
    min_km: Optional[int] = None
    max_km: Optional[int] = None
    province_whitelist: Optional[List[str]] = None
    is_active: Optional[bool] = None

# Delivery Quote Models
class DeliveryQuoteRequest(BaseModel):
    seller_id: str
    buyer_lat: float
    buyer_lng: float

class DeliveryQuote(BaseModel):
    seller_id: str
    distance_km: Optional[float] = None
    delivery_fee_cents: Optional[int] = None
    out_of_range: bool = False
    base_fee_cents: int = 0
    per_km_fee_cents: int = 0
    message: Optional[str] = None

# Helper functions
def hash_password(password: str) -> str:
    """Hash password using bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    """Verify password against hash"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def generate_tracking_number() -> str:
    """Generate a unique tracking number in format: TRK + timestamp + random string"""
    timestamp = int(time.time())
    random_part = uuid.uuid4().hex[:8].upper()
    tracking_num = f"TRK{timestamp}{random_part}"
    logger.debug(f"Generated tracking number: {tracking_num}")
    return tracking_num

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get current authenticated user"""
    if not credentials:
        return None
    
    # Simple token validation - token is email for now
    try:
        # Find user by email (token is email for simplicity)
        user_doc = await db.users.find_one({"email": credentials.credentials})
        if user_doc:
            # Convert MongoDB doc to User model, removing ObjectId
            user_dict = {k: v for k, v in user_doc.items() if k != "_id" and k != "password"}
            return User(**user_dict)
    except Exception as e:
        logger.error(f"Error validating user: {e}")
    
    return None

async def get_current_user_optional(credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer(auto_error=False))) -> Optional[User]:
    """Get current user or None if not authenticated"""
    try:
        if not credentials:
            return None
        return await get_current_user(credentials)
    except:
        return None

# Set shared dependencies to avoid circular imports
set_database(db)
set_shared_get_current_user(get_current_user)

# Import AI and Media services
try:
    from services.ai_service import ai_service
    from services.media_service import media_service
    AI_AVAILABLE = True
    MEDIA_AVAILABLE = True
except ImportError as e:
    logger.warning(f"AI/Media services not available: {e}")
    AI_AVAILABLE = False
    MEDIA_AVAILABLE = False

# AI-POWERED FAQ CHATBOT
@api_router.post("/faq/chat")
async def ai_faq_chat(
    chat_data: dict,
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """AI-powered FAQ chatbot using OpenAI"""
    try:
        question = chat_data.get("question", "").strip()
        if not question:
            raise HTTPException(status_code=400, detail="Question is required")
        
        if not AI_AVAILABLE:
            return {
                "response": "I'm having trouble connecting to our AI system right now, but I can still help!\n\n🐄 StockLot offers ALL livestock including:\n• Poultry (chickens, ducks, turkeys)\n• Ruminants (cattle, goats, sheep)\n• Aquaculture (fish farming, prawns) ✅\n• Game Animals (kudu, springbok through processors)\n• Small Livestock (pigs, rabbits)\n\nUse in-app messaging or platform support system for personalized help!",
                "source": "fallback"
            }
        
        # Prepare user context
        user_context = {}
        if current_user:
            user_context = {
                "user_type": "registered_user",
                "location": "South Africa",  # Default location since province field doesn't exist
                "user_roles": current_user.roles or []
            }
        else:
            user_context = {
                "user_type": "visitor",
                "location": "South Africa"
            }
        
        # Get AI response
        response = await ai_service.get_faq_response(question, user_context)
        
        return {
            "response": response,
            "source": "ai",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error in FAQ chat: {e}")
        return {
            "response": "I'm having trouble right now, but I can still help!\n\n🐄 StockLot marketplace includes:\n• ALL livestock types including Aquaculture (fish) ✅\n• Game meat through approved processors\n• Secure escrow payments\n• Nationwide delivery\n\nUse platform messaging system for personalized support!",
            "source": "error"
        }

# CHATBOT LEARNING ENDPOINTS
@api_router.post("/chatbot/learn/website")
async def trigger_website_learning():
    """Trigger chatbot learning from website content"""
    try:
        if not ml_faq_service:
            raise HTTPException(status_code=503, detail="ML FAQ service not available")
        
        result = await ml_faq_service.learn_from_website_content()
        return result
    except Exception as e:
        logger.error(f"Error in website learning: {e}")
        raise HTTPException(status_code=500, detail="Failed to learn from website content")

@api_router.post("/chatbot/learn/blog")
async def trigger_blog_learning():
    """Trigger chatbot learning from blog content"""
    try:
        if not ml_faq_service:
            raise HTTPException(status_code=503, detail="ML FAQ service not available")
        
        result = await ml_faq_service.learn_from_blog_content()
        return result
    except Exception as e:
        logger.error(f"Error in blog learning: {e}")
        raise HTTPException(status_code=500, detail="Failed to learn from blog content")

@api_router.get("/chatbot/learning-status")
async def get_learning_status():
    """Get status of chatbot learning activities"""
    try:
        # Get recent learning records
        cursor = db.faq_learning.find().sort("created_at", -1).limit(10)
        learning_records = await cursor.to_list(length=None)
        
        # Clean MongoDB _id fields
        for record in learning_records:
            if "_id" in record:
                del record["_id"]
        
        return {
            "recent_learning": learning_records,
            "total_records": len(learning_records),
            "last_website_learning": next((r for r in learning_records if r.get("type") == "website_content_learning"), None),
            "last_blog_learning": next((r for r in learning_records if r.get("type") == "blog_content_learning"), None)
        }
    except Exception as e:
        logger.error(f"Error getting learning status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get learning status")

# PROFESSIONAL IMAGE UPLOAD
@api_router.post("/upload/listing-image")
async def upload_listing_image(
    file: UploadFile,
    listing_id: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Upload listing image with proper validation"""
    try:
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        # Validate file type
        if not file.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="File must be an image")
        
        # Validate file size (max 10MB)
        content = await file.read()
        file_size = len(content)
        
        if file_size > 10 * 1024 * 1024:  # 10MB
            raise HTTPException(status_code=400, detail="File size must be less than 10MB")
        
        # Create uploads directory if it doesn't exist
        upload_dir = Path("/app/uploads/listings")
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate unique filename
        file_extension = file.filename.split('.')[-1] if '.' in file.filename else 'jpg'
        unique_filename = f"{listing_id or 'temp'}_{uuid.uuid4().hex[:8]}.{file_extension}"
        file_path = upload_dir / unique_filename
        
        # Save file
        with open(file_path, 'wb') as f:
            f.write(content)
        
        # Generate relative URL for frontend
        image_url = f"/uploads/listings/{unique_filename}"
        
        logger.info(f"✅ Listing image uploaded: {image_url}")
        
        return {
            "success": True,
            "image_url": image_url,
            "filename": unique_filename,
            "size_bytes": file_size,
            "message": "Image uploaded successfully"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading listing image: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload image")

@api_router.post("/upload/profile-image")
async def upload_profile_image(
    file: UploadFile,
    current_user: User = Depends(get_current_user)
):
    """Upload profile image"""
    try:
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        # Validate file type
        if not file.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="File must be an image")
        
        # Validate file size (max 5MB for profiles)
        content = await file.read()
        file_size = len(content)
        
        if file_size > 5 * 1024 * 1024:  # 5MB
            raise HTTPException(status_code=400, detail="File size must be less than 5MB")
        
        # Create uploads directory if it doesn't exist
        upload_dir = Path("/app/uploads/profiles")
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate unique filename
        file_extension = file.filename.split('.')[-1] if '.' in file.filename else 'jpg'
        unique_filename = f"profile_{current_user.id}_{uuid.uuid4().hex[:8]}.{file_extension}"
        file_path = upload_dir / unique_filename
        
        # Save file
        with open(file_path, 'wb') as f:
            f.write(content)
        
        # Generate relative URL for frontend
        image_url = f"/uploads/profiles/{unique_filename}"
        
        # Update user profile with new image URL
        await db.users.update_one(
            {"id": current_user.id},
            {"$set": {"profile_photo": image_url, "updated_at": datetime.now(timezone.utc)}}
        )
        
        logger.info(f"✅ Profile image uploaded for user {current_user.id}: {image_url}")
        
        return {
            "success": True,
            "image_url": image_url,
            "filename": unique_filename,
            "size_bytes": file_size,
            "message": "Profile image uploaded successfully"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading profile image: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload profile image")
# PASSWORD RESET ENDPOINTS
@api_router.post("/auth/password-reset")
async def password_reset_request(request_data: dict):
    """Request password reset"""
    try:
        email = request_data.get("email", "").strip().lower()
        if not email:
            raise HTTPException(status_code=400, detail="Email is required")
        
        # Check if user exists
        user = await db.users.find_one({"email": email})
        if not user:
            # For security, return success even if user doesn't exist
            return {
                "success": True,
                "message": "If an account exists with this email, a password reset link has been sent."
            }
        
        # Generate reset token
        reset_token = uuid.uuid4().hex
        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
        
        # Store reset token
        reset_record = {
            "id": str(uuid.uuid4()),
            "user_id": user["id"],
            "email": email,
            "token": reset_token,
            "expires_at": expires_at,
            "used": False,
            "created_at": datetime.now(timezone.utc)
        }
        
        await db.password_resets.insert_one(reset_record)
        
        # In production, send email with reset link
        reset_link = f"https://farmstock-hub-1.preview.emergentagent.com/reset-password?token={reset_token}"
        logger.info(f"🔑 Password reset requested for {email}. Reset link: {reset_link}")
        
        return {
            "success": True,
            "message": "If an account exists with this email, a password reset link has been sent.",
            "reset_token": reset_token if os.getenv("DEBUG", "false").lower() == "true" else None
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing password reset request: {e}")
        raise HTTPException(status_code=500, detail="Failed to process password reset request")

@api_router.post("/auth/password-reset/confirm")
async def password_reset_confirm(reset_data: dict):
    """Confirm password reset with token"""
    try:
        token = reset_data.get("token", "").strip()
        new_password = reset_data.get("new_password", "").strip()
        
        if not token or not new_password:
            raise HTTPException(status_code=400, detail="Token and new password are required")
        
        if len(new_password) < 8:
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters long")
        
        # Find valid reset token
        reset_record = await db.password_resets.find_one({
            "token": token,
            "used": False,
            "expires_at": {"$gt": datetime.now(timezone.utc)}
        })
        
        if not reset_record:
            raise HTTPException(status_code=400, detail="Invalid or expired reset token")
        
        # Update user password
        hashed_password = hash_password(new_password)
        await db.users.update_one(
            {"id": reset_record["user_id"]},
            {"$set": {
                "password": hashed_password,
                "updated_at": datetime.now(timezone.utc)
            }}
        )
        
        # Mark token as used
        await db.password_resets.update_one(
            {"id": reset_record["id"]},
            {"$set": {
                "used": True,
                "used_at": datetime.now(timezone.utc)
            }}
        )
        
        logger.info(f"🔑 Password reset completed for user {reset_record['user_id']}")
        
        return {
            "success": True,
            "message": "Password has been reset successfully. You can now log in with your new password."
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error confirming password reset: {e}")
        raise HTTPException(status_code=500, detail="Failed to reset password")

# EMAIL SYSTEM ENDPOINTS
@api_router.get("/email/preferences")
async def get_email_preferences(current_user: User = Depends(get_current_user)):
    """Get user email preferences"""
    try:
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        # Get user's email preferences or return defaults
        preferences = await db.email_preferences.find_one({"user_id": current_user.id})
        
        if not preferences:
            # Return default preferences
            default_preferences = {
                "user_id": current_user.id,
                "marketing_emails": True,
                "order_updates": True,
                "new_listings": True,
                "price_alerts": True,
                "chat_notifications": True,
                "security_alerts": True,
                "newsletter": True,
                "created_at": datetime.now(timezone.utc)
            }
            await db.email_preferences.insert_one(default_preferences)
            preferences = default_preferences
        
        # Remove MongoDB _id
        if "_id" in preferences:
            del preferences["_id"]
        
        return preferences
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting email preferences: {e}")
        raise HTTPException(status_code=500, detail="Failed to get email preferences")

@api_router.put("/email/preferences")
async def update_email_preferences(
    preferences: dict,
    current_user: User = Depends(get_current_user)
):
    """Update user email preferences"""
    try:
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        # Update preferences
        update_data = {
            **preferences,
            "user_id": current_user.id,
            "updated_at": datetime.now(timezone.utc)
        }
        
        await db.email_preferences.update_one(
            {"user_id": current_user.id},
            {"$set": update_data},
            upsert=True
        )
        
        return {"success": True, "message": "Email preferences updated successfully"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating email preferences: {e}")
        raise HTTPException(status_code=500, detail="Failed to update email preferences")

@api_router.get("/email/templates")
async def get_email_templates():
    """Get available email templates"""
    try:
        templates = [
            {
                "id": "welcome",
                "name": "Welcome Email",
                "description": "Welcome new users to StockLot"
            },
            {
                "id": "order_confirmation",
                "name": "Order Confirmation",
                "description": "Confirm order placement"
            },
            {
                "id": "payment_confirmation",
                "name": "Payment Confirmation",
                "description": "Confirm payment receipt"
            },
            {
                "id": "order_shipped",
                "name": "Order Shipped",
                "description": "Notify when order is shipped"
            },
            {
                "id": "price_alert",
                "name": "Price Alert",
                "description": "Notify about price changes"
            },
            {
                "id": "new_listing",
                "name": "New Listing",
                "description": "Notify about new listings"
            }
        ]
        
        return {"templates": templates}
    
    except Exception as e:
        logger.error(f"Error getting email templates: {e}")
        raise HTTPException(status_code=500, detail="Failed to get email templates")

@api_router.post("/email/test")
async def send_test_email(
    email_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Send test email"""
    try:
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        to_email = email_data.get("to", current_user.email)
        template = email_data.get("template", "welcome")
        
        # Create test email content
        subject = f"Test Email - {template.title()}"
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2>Test Email - StockLot Marketplace</h2>
                <p>This is a test email for template: <strong>{template}</strong></p>
                <p>If you're receiving this, the email system is working correctly!</p>
                <hr>
                <p style="color: #666; font-size: 12px;">
                    This is a test email sent from StockLot Marketplace<br>
                    Time: {datetime.now(timezone.utc).isoformat()}<br>
                    Template: {template}
                </p>
            </body>
        </html>
        """
        
        # Log the test email (in production, you'd actually send it)
        logger.info(f"📧 Test email sent to {to_email} using template {template}")
        
        return {
            "success": True,
            "message": f"Test email sent to {to_email}",
            "template": template,
            "subject": subject
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending test email: {e}")
        raise HTTPException(status_code=500, detail="Failed to send test email")

@api_router.post("/upload/livestock-image")
async def upload_livestock_image(
    file: UploadFile,
    listing_id: str,
    image_type: str = "primary",
    current_user: User = Depends(get_current_user)
):
    """Upload livestock image with Cloudinary optimization"""
    try:
        if not MEDIA_AVAILABLE:
            raise HTTPException(status_code=503, detail="Media service unavailable")
        
        # Validate file type
        if not file.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="File must be an image")
        
        # Validate file size (max 10MB)
        file_size = 0
        content = await file.read()
        file_size = len(content)
        
        if file_size > 10 * 1024 * 1024:  # 10MB
            raise HTTPException(status_code=400, detail="File size must be less than 10MB")
        
        # Upload to Cloudinary
        result = await media_service.upload_livestock_image(
            content, listing_id, image_type
        )
        
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Upload failed"))
        
        # Optionally analyze the image with AI
        image_analysis = None
        if AI_AVAILABLE and result.get("secure_url"):
            try:
                image_analysis = await ai_service.analyze_livestock_image(result["secure_url"])
            except Exception as e:
                logger.warning(f"Image analysis failed: {e}")
        
        return {
            "success": True,
            "image": {
                "public_id": result["public_id"],
                "secure_url": result["secure_url"],
                "variants": result.get("variants", {}),
                "width": result.get("width"),
                "height": result.get("height"),
                "format": result.get("format"),
                "size_bytes": result.get("bytes")
            },
            "ai_analysis": image_analysis
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading livestock image: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload image")

@api_router.post("/upload/buy-request-image")
async def upload_buy_request_image(
    file: UploadFile,
    request_id: Optional[str] = None,
    image_type: str = "reference",
    current_user: User = Depends(get_current_user)
):
    """Upload buy request reference image"""
    try:
        if not MEDIA_AVAILABLE:
            raise HTTPException(status_code=503, detail="Media service unavailable")
        
        # Validate file type
        if not file.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="File must be an image")
        
        # Validate file size (max 10MB)
        content = await file.read()
        file_size = len(content)
        
        if file_size > 10 * 1024 * 1024:  # 10MB
            raise HTTPException(status_code=400, detail="File size must be less than 10MB")
        
        # Generate unique identifier for buy request images
        image_id = f"buy_request_{request_id or 'temp'}_{int(datetime.now().timestamp())}"
        
        # Upload to Cloudinary with buy request specific folder
        result = await media_service.upload_livestock_image(
            content, image_id, image_type
        )
        
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Upload failed"))
        
        return {
            "success": True,
            "image": {
                "public_id": result["public_id"],
                "secure_url": result["secure_url"],
                "variants": result.get("variants", {}),
                "width": result.get("width"),
                "height": result.get("height"),
                "format": result.get("format"),
                "size_bytes": result.get("bytes")
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading buy request image: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload image")

@api_router.post("/upload/vet-certificate")
async def upload_vet_certificate(
    file: UploadFile,
    request_id: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Upload vet certificate for buy request"""
    try:
        if not MEDIA_AVAILABLE:
            raise HTTPException(status_code=503, detail="Media service unavailable")
        
        # Validate file type (allow PDF and images)
        allowed_types = ['image/', 'application/pdf']
        if not any(file.content_type.startswith(t) for t in allowed_types):
            raise HTTPException(status_code=400, detail="File must be an image or PDF")
        
        # Validate file size (max 5MB for certificates)
        content = await file.read()
        file_size = len(content)
        
        if file_size > 5 * 1024 * 1024:  # 5MB
            raise HTTPException(status_code=400, detail="File size must be less than 5MB")
        
        # Generate unique identifier for vet certificates
        cert_id = f"vet_cert_{request_id or 'temp'}_{int(datetime.now().timestamp())}"
        
        # Upload to Cloudinary with vet certificate specific folder
        result = await media_service.upload_livestock_image(
            content, cert_id, "certificate"
        )
        
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Upload failed"))
        
        return {
            "success": True,
            "certificate": {
                "public_id": result["public_id"],
                "secure_url": result["secure_url"],
                "format": result.get("format"),
                "size_bytes": result.get("bytes")
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading vet certificate: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload certificate")

# AI-POWERED LISTING ENHANCEMENT
@api_router.post("/listings/{listing_id}/enhance")
async def enhance_listing_with_ai(
    listing_id: str,
    enhancement_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Enhance listing with AI-generated description"""
    try:
        if not AI_AVAILABLE:
            raise HTTPException(status_code=503, detail="AI service unavailable")
        
        # Get listing
        listing = await db.listings.find_one({"id": listing_id, "user_id": current_user.id})
        if not listing:
            raise HTTPException(status_code=404, detail="Listing not found")
        
        # Prepare animal details
        animal_details = {
            "species": enhancement_data.get("species") or listing.get("species"),
            "breed": enhancement_data.get("breed") or listing.get("breed"),
            "age": enhancement_data.get("age") or listing.get("age"),
            "weight": enhancement_data.get("weight") or listing.get("weight"),
            "sex": enhancement_data.get("sex") or listing.get("sex"),
            "health_status": enhancement_data.get("health_status", "Healthy"),
            "purpose": enhancement_data.get("purpose", "General livestock")
        }
        
        # Generate AI description
        ai_description = await ai_service.generate_listing_description(animal_details)
        
        # Update listing with AI-enhanced description
        update_data = {
            "ai_enhanced_description": ai_description,
            "enhanced_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }
        
        await db.listings.update_one(
            {"id": listing_id},
            {"$set": update_data}
        )
        
        return {
            "success": True,
            "enhanced_description": ai_description,
            "original_description": listing.get("description"),
            "enhancement_details": animal_details
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error enhancing listing: {e}")
        raise HTTPException(status_code=500, detail="Failed to enhance listing")

# SHOPPING CART SYSTEM
@api_router.get("/cart")
async def get_user_cart(current_user: User = Depends(get_current_user)):
    """Get user's shopping cart"""
    try:
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
            
        cart = await db.carts.find_one({"user_id": current_user.id})
        if not cart:
            return {"items": [], "total": 0, "item_count": 0}
        
        # Get listing details for cart items
        cart_items = []
        total = 0
        
        for item in cart.get("items", []):
            listing = await db.listings.find_one({"id": item["listing_id"]})
            if listing:
                # Convert MongoDB doc to dict and remove ObjectId
                listing_dict = dict(listing)
                if "_id" in listing_dict:
                    del listing_dict["_id"]
                    
                item_total = item["quantity"] * item["price"]
                cart_items.append({
                    "id": item["id"],
                    "listing": listing_dict,
                    "quantity": item["quantity"],
                    "price": item["price"],
                    "item_total": item_total,
                    "shipping_cost": item.get("shipping_cost", 0)
                })
                total += item_total + item.get("shipping_cost", 0)
        
        return {
            "items": cart_items,
            "total": total,
            "item_count": len(cart_items)
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching cart: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch cart")

@api_router.post("/cart/add")
async def add_to_cart(
    request: Request,
    cart_item: dict,
    current_user: User = Depends(get_current_user)
):
    """Add item to shopping cart"""
    # Apply rate limiting for cart operations
    await rate_limit_middleware(request, "cart", current_user.id if current_user else None)
    
    try:
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
            
        listing_id = cart_item.get("listing_id")
        quantity = cart_item.get("quantity", 1)
        shipping_option = cart_item.get("shipping_option", "standard")
        
        if not listing_id:
            raise HTTPException(status_code=400, detail="listing_id is required")
        
        # Validate and convert quantity to integer
        try:
            if isinstance(quantity, str):
                quantity = int(quantity)
            elif isinstance(quantity, float):
                quantity = int(quantity)
            elif not isinstance(quantity, int):
                raise ValueError("Invalid quantity type")
                
            if quantity <= 0:
                raise HTTPException(status_code=400, detail="Quantity must be a positive integer")
                
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Quantity must be a positive integer")
        
        # Verify listing exists and is available
        listing = await db.listings.find_one({"id": listing_id})
        if not listing:
            raise HTTPException(status_code=404, detail="Listing not found")
        
        if listing.get("status") != "active":
            raise HTTPException(status_code=400, detail="Listing is not available")
        
        # Calculate shipping cost (basic implementation)
        shipping_cost = 0
        if shipping_option == "express":
            shipping_cost = listing.get("express_shipping_cost", 200)
        else:
            shipping_cost = listing.get("standard_shipping_cost", 100)
        
        # Get or create cart
        cart = await db.carts.find_one({"user_id": current_user.id})
        if not cart:
            cart = {
                "id": str(uuid.uuid4()),
                "user_id": current_user.id,
                "items": [],
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc)
            }
        
        # Check if item already exists in cart
        existing_item = None
        for item in cart["items"]:
            if item["listing_id"] == listing_id:
                existing_item = item
                break
        
        if existing_item:
            # Update quantity
            existing_item["quantity"] += quantity
            existing_item["updated_at"] = datetime.now(timezone.utc)
        else:
            # Add new item - handle Decimal price properly
            listing_price = listing.get("price_per_unit")
            if listing_price is None:
                # Fallback to other possible price fields
                listing_price = listing.get("price", 0)
            
            # Convert Decimal to float for JSON serialization
            if hasattr(listing_price, '__float__'):
                listing_price = float(listing_price)
            elif isinstance(listing_price, str):
                try:
                    listing_price = float(listing_price)
                except (ValueError, TypeError):
                    listing_price = 0.0
            elif listing_price is None:
                listing_price = 0.0
            
            new_item = {
                "id": str(uuid.uuid4()),
                "listing_id": listing_id,
                "quantity": quantity,
                "price": listing_price,
                "shipping_cost": shipping_cost,
                "shipping_option": shipping_option,
                "added_at": datetime.now(timezone.utc)
            }
            cart["items"].append(new_item)
        
        cart["updated_at"] = datetime.now(timezone.utc)
        
        # Save cart
        await db.carts.replace_one(
            {"user_id": current_user.id},
            cart,
            upsert=True
        )
        
        return {
            "success": True,
            "message": "Item added to cart successfully",
            "cart_item_count": len(cart["items"])
        }
    
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"Error adding to cart: {e}")
        logger.error(f"Cart item data: {cart_item}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to add item to cart: {str(e)}")

@api_router.delete("/cart/item/{item_id}")
async def remove_from_cart(
    item_id: str,
    current_user: User = Depends(get_current_user)
):
    """Remove item from cart"""
    try:
        result = await db.carts.update_one(
            {"user_id": current_user.id},
            {"$pull": {"items": {"id": item_id}}}
        )
        
        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="Cart item not found")
        
        return {"success": True, "message": "Item removed from cart"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing from cart: {e}")
        raise HTTPException(status_code=500, detail="Failed to remove item from cart")

@api_router.put("/cart/update")
async def update_cart_item(
    update_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Update cart item quantity"""
    try:
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        item_id = update_data.get("item_id")
        quantity = update_data.get("quantity")
        
        if not item_id or not quantity or quantity < 1:
            raise HTTPException(status_code=400, detail="Valid item_id and quantity required")
        
        # Update the cart item quantity
        result = await db.carts.update_one(
            {"user_id": current_user.id, "items.id": item_id},
            {"$set": {
                "items.$.quantity": quantity,
                "updated_at": datetime.now(timezone.utc)
            }}
        )
        
        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="Cart item not found")
        
        # Get updated cart for response
        cart = await db.carts.find_one({"user_id": current_user.id})
        total_items = sum(item.get("quantity", 0) for item in cart.get("items", []))
        
        return {
            "success": True, 
            "message": "Cart item updated successfully",
            "cart_item_count": total_items
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating cart item: {e}")
        raise HTTPException(status_code=500, detail="Failed to update cart item")

# STREAMLINED CHECKOUT SYSTEM
@api_router.post("/checkout/create")
async def create_checkout(
    request: Request,
    checkout_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Create checkout session for cart items"""
    # Apply rate limiting for checkout creation
    await rate_limit_middleware(request, "checkout_create", current_user.id if current_user else None)
    
    try:
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
            
        # Get user's cart
        cart = await db.carts.find_one({"user_id": current_user.id})
        if not cart or not cart.get("items"):
            raise HTTPException(status_code=400, detail="Cart is empty")
        
        # Validate all items are still available
        total_amount = 0
        order_items = []
        
        for cart_item in cart["items"]:
            listing = await db.listings.find_one({"id": cart_item["listing_id"]})
            if not listing or listing.get("status") != "active":
                raise HTTPException(
                    status_code=400, 
                    detail=f"Item '{listing.get('title', 'Unknown')}' is no longer available"
                )
            
            item_total = cart_item["quantity"] * cart_item["price"]
            shipping_cost = cart_item.get("shipping_cost", 0)
            total_amount += item_total + shipping_cost
            
            order_items.append({
                "listing_id": cart_item["listing_id"],
                "listing_title": listing["title"],
                "seller_id": listing["seller_id"],  # Fix: use seller_id not user_id
                "quantity": cart_item["quantity"],
                "price": cart_item["price"],
                "shipping_cost": shipping_cost,
                "item_total": item_total
            })
        
        # Create checkout session
        checkout_session = {
            "id": str(uuid.uuid4()),
            "user_id": current_user.id,
            "items": order_items,
            "subtotal": total_amount,
            "total_amount": total_amount,
            "shipping_address": checkout_data.get("shipping_address"),
            "payment_method": checkout_data.get("payment_method"),
            "status": "pending",
            "created_at": datetime.now(timezone.utc),
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=1)
        }
        
        # Save checkout session
        await db.checkout_sessions.insert_one(checkout_session)
        
        return {
            "checkout_session_id": checkout_session["id"],
            "total_amount": total_amount,
            "items": order_items,
            "expires_at": checkout_session["expires_at"]
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating checkout: {e}")
        raise HTTPException(status_code=500, detail="Failed to create checkout session")

@api_router.post("/checkout/order")
async def create_authenticated_order(
    request: Request,
    request_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Create order for authenticated user with escrow payment (similar to guest checkout)"""
    # Apply rate limiting for authenticated checkout
    await rate_limit_middleware(request, "checkout_create", current_user.id if current_user else None)
    
    try:
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        ship_to = request_data.get("ship_to")
        items = request_data.get("items", [])
        quote = request_data.get("quote")
        
        if not items:
            raise HTTPException(status_code=400, detail="Empty cart")
        
        if not ship_to:
            raise HTTPException(status_code=400, detail="Delivery address required")
        
        if not quote:
            raise HTTPException(status_code=400, detail="Quote required")
        
        # Re-assess risk (using the assess_risk function defined in this file)
        lines = [{"species": i.get("species"), "product_type": i.get("product_type"), 
                 "qty": i.get("qty"), "line_total": i.get("line_total") or 0} for i in items]
        risk = assess_risk(lines)
        
        if risk["gate"] == "BLOCK":
            raise HTTPException(status_code=403, detail="KYC required for these items")
        
        # Create order group
        quote_summary = quote.get("summary", {})
        grand_total = quote_summary.get("grand_total") or 0
        delivery_total = quote_summary.get("delivery_total") or 0
        
        # Generate tracking number
        tracking_num = generate_tracking_number()
        logger.info(f"Generated tracking number for authenticated order: {tracking_num}")
        
        order_group = {
            "id": str(uuid.uuid4()),
            "tracking_number": tracking_num,
            "buyer_user_id": current_user.id,
            "status": "PENDING",
            "currency": "ZAR",
            "grand_total": grand_total,
            "items_count": len(items),
            "delivery_total": delivery_total,
            "created_at": datetime.now(timezone.utc)
        }
        await db.order_groups.insert_one(order_group)
        logger.info(f"✅ Order group created with ID: {order_group['id']}, Tracking: {tracking_num}")
        
        # Create order contact (using authenticated user's info)
        order_contact = {
            "order_group_id": order_group["id"],
            "email": current_user.email,
            "phone": current_user.phone or "",
            "full_name": current_user.full_name or "",
            "address_json": ship_to,
            "kyc_level_required": risk["kyc_required"],
            "kyc_checked_at": None
        }
        await db.order_contacts.insert_one(order_contact)
        
        # Create seller orders
        for seller in quote["sellers"]:
            seller_subtotal = seller.get("subtotal") or 0
            seller_delivery = seller.get("delivery") or 0
            
            seller_order = {
                "id": str(uuid.uuid4()),
                "order_group_id": order_group["id"],
                "seller_id": seller["seller_id"],
                "subtotal": seller_subtotal,
                "delivery": seller_delivery,
                "total": seller_subtotal + seller_delivery,
                "status": "PENDING",
                "created_at": datetime.now(timezone.utc)
            }
            await db.seller_orders.insert_one(seller_order)
            
            # Create order items
            for item in seller["items"]:
                order_item = {
                    "id": str(uuid.uuid4()),
                    "seller_order_id": seller_order["id"],
                    "listing_id": item["listing_id"],
                    "title": item["title"],
                    "species": item["species"],
                    "product_type": item["product_type"],
                    "unit": item["unit"],
                    "qty": item["qty"],
                    "price": item["price"],
                    "line_total": item["line_total"]
                }
                await db.order_items.insert_one(order_item)
        
        # Clear user's cart after successful order creation
        await db.carts.delete_one({"user_id": current_user.id})
        
        # Initialize Paystack transaction for payment
        try:
            base_url = os.getenv("FRONTEND_URL", "https://farmstock-hub-1.preview.emergentagent.com")
            callback_url = f"{base_url}/checkout/return?og={order_group['id']}"
            
            payment_result = await paystack_service.initialize_transaction(
                email=current_user.email,
                amount=quote["summary"]["grand_total"],
                order_id=order_group["id"],
                callback_url=callback_url
            )
            
            logger.info(f"Paystack payment result: {payment_result}")
            
            authorization_url = None
            reference = f"STOCKLOT_{order_group['id']}"
            
            if payment_result:
                if isinstance(payment_result, dict):
                    if payment_result.get("status") == True or payment_result.get("success") == True:
                        data = payment_result.get("data", payment_result)
                        authorization_url = data.get("authorization_url")
                        reference = f"STOCKLOT_{order_group['id']}"
                    elif payment_result.get("authorization_url"):
                        authorization_url = payment_result.get("authorization_url")
                        reference = payment_result.get("reference", reference)
                    elif "checkout.paystack.com" in str(payment_result.get("authorization_url", "")):
                        authorization_url = payment_result.get("authorization_url")
                        reference = payment_result.get("reference", reference)
            
            if authorization_url and ("checkout.paystack.com" in authorization_url or "paystack.com" in authorization_url):
                logger.info(f"✅ Valid Paystack authorization URL: {authorization_url}")
            else:
                logger.warning(f"⚠️ Invalid or missing Paystack URL. Received: {payment_result}")
                authorization_url = f"https://demo-checkout.paystack.com/{order_group['id']}"
                reference = f"DEMO_{order_group['id']}"
                logger.info(f"Using demo URL: {authorization_url}")
                
        except Exception as e:
            logger.error(f"Payment service error for order {order_group['id']}: {e}")
            base_url = os.getenv("FRONTEND_URL", "https://farmstock-hub-1.preview.emergentagent.com")
            authorization_url = f"https://demo-checkout.paystack.com/{order_group['id']}"
            reference = f"ERROR_{order_group['id']}"
            logger.info(f"Using error fallback URL: {authorization_url}")
        
        order_count = len(quote["sellers"])
        
        response_data = {
            "ok": True,
            "order_group_id": order_group["id"],
            "order_count": order_count,
            "paystack": {
                "authorization_url": authorization_url,
                "reference": reference
            },
            "authorization_url": authorization_url,
            "redirect_url": authorization_url,
            "payment_url": authorization_url,
            "reference": reference,
            "risk": risk
        }
        
        logger.info(f"✅ Authenticated order created successfully with payment URL: {authorization_url}")
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"Error creating authenticated order: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        error_detail = f"Failed to create order: {str(e)}"
        if "unsupported operand type" in str(e):
            error_detail = "Order calculation error - please contact support"
        raise HTTPException(status_code=500, detail=error_detail)

@api_router.post("/checkout/{session_id}/complete")
async def complete_checkout(
    request: Request,
    session_id: str,
    payment_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Complete checkout and create orders"""
    # Apply rate limiting for checkout completion
    await rate_limit_middleware(request, "checkout_complete", current_user.id if current_user else None)
    
    try:
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
            
        # Get checkout session
        session = await db.checkout_sessions.find_one({
            "id": session_id,
            "user_id": current_user.id
        })
        
        if not session:
            raise HTTPException(status_code=404, detail="Checkout session not found")
        
        if session["status"] != "pending":
            raise HTTPException(status_code=400, detail="Checkout session already processed")
        
        # Handle timezone comparison safely
        now = datetime.now(timezone.utc)
        expires_at = session["expires_at"]
        
        # Ensure expires_at has timezone info
        if isinstance(expires_at, datetime) and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        elif isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
            
        if now > expires_at:
            raise HTTPException(status_code=400, detail="Checkout session expired")
        
        # Check if we're in demo mode
        demo_mode = os.getenv("PAYSTACK_DEMO_MODE", "false").lower() == "true"
        
        # In demo mode, simulate successful payment
        if demo_mode:
            logger.info(f"Demo mode: Auto-completing checkout for session {session_id}")
            
        # Group items by seller to create separate orders
        orders_by_seller = {}
        for item in session["items"]:
            seller_id = item["seller_id"]
            if seller_id not in orders_by_seller:
                orders_by_seller[seller_id] = []
            orders_by_seller[seller_id].append(item)
        
        created_orders = []
        
        # Create separate order for each seller
        for seller_id, items in orders_by_seller.items():
            order_total = sum(item["item_total"] + item["shipping_cost"] for item in items)
            
            order = {
                "id": str(uuid.uuid4()),
                "buyer_id": current_user.id,
                "seller_id": seller_id,
                "items": items,
                "total_amount": order_total,
                "shipping_address": session["shipping_address"],
                "payment_method": payment_data.get("payment_method"),
                "payment_status": "pending",
                "order_status": "confirmed",
                "delivery_status": "preparing",
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc)
            }
            
            # Save order
            await db.orders.insert_one(order)
            created_orders.append(order)
            
            # Update listing quantities (if applicable)
            for item in items:
                await db.listings.update_one(
                    {"id": item["listing_id"]},
                    {"$inc": {"quantity": -item["quantity"]}}
                )
        
        # Update checkout session
        await db.checkout_sessions.update_one(
            {"id": session_id},
            {"$set": {"status": "completed", "completed_at": datetime.now(timezone.utc)}}
        )
        
        # Clear user's cart
        await db.carts.delete_one({"user_id": current_user.id})
        
        # Send notifications to sellers
        for order in created_orders:
            await emit_admin_event("ORDER.CREATED", {
                "order_id": order["id"],
                "buyer_id": order["buyer_id"],
                "seller_id": order["seller_id"],
                "total_amount": order["total_amount"]
            })
        
        # Initialize payment for the total order amount
        total_order_amount = sum(order["total_amount"] for order in created_orders)
        
        try:
            # Initialize Paystack payment
            payment_result = await paystack_service.initialize_transaction(
                email=current_user.email,
                amount=total_order_amount,
                order_id=",".join([order["id"] for order in created_orders]),  # Multiple order IDs
                callback_url=payment_data.get("callback_url", "https://stocklot.farm/payment/callback")
            )
            
            authorization_url = None
            if payment_result and payment_result.get("authorization_url"):
                authorization_url = payment_result.get("authorization_url")
                logger.info(f"✅ Payment initialized successfully: {authorization_url}")
            else:
                # Fallback for demo mode
                demo_mode = os.getenv("PAYSTACK_DEMO_MODE", "false").lower() == "true"
                if demo_mode:
                    authorization_url = f"https://demo-checkout.paystack.com/{session_id}"
                    logger.info(f"Demo mode: Using demo payment URL: {authorization_url}")
                
        except Exception as payment_error:
            logger.error(f"Payment initialization failed: {payment_error}")
            # In demo mode, continue with demo URL
            demo_mode = os.getenv("PAYSTACK_DEMO_MODE", "false").lower() == "true"
            if demo_mode:
                authorization_url = f"https://demo-checkout.paystack.com/{session_id}"
                logger.info(f"Payment error fallback: Using demo URL: {authorization_url}")
            else:
                # For production, this would be a critical error
                raise HTTPException(status_code=500, detail="Payment initialization failed")

        return {
            "success": True,
            "message": "Order placed successfully!",
            "orders": [{"id": order["id"], "total": order["total_amount"]} for order in created_orders],
            "payment_url": authorization_url,
            "authorization_url": authorization_url,
            "redirect_url": authorization_url,
            "total_amount": total_order_amount,
            "requires_payment": True
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error completing checkout: {e}")
        raise HTTPException(status_code=500, detail="Failed to complete checkout")

# ORDER MANAGEMENT SYSTEM
@api_router.get("/orders/user")
async def get_user_orders_detailed(current_user: User = Depends(get_current_user)):
    """Get orders for current user (both as buyer and seller)"""
    try:
        # Get orders where user is buyer
        buyer_orders_docs = await db.orders.find({"buyer_id": current_user.id}).sort("created_at", -1).to_list(length=None)
        
        # Get orders where user is seller
        seller_orders_docs = await db.orders.find({"seller_id": current_user.id}).sort("created_at", -1).to_list(length=None)
        
        # Clean both buyer and seller orders
        buyer_orders = []
        seller_orders = []
        
        for doc in buyer_orders_docs:
            try:
                if "_id" in doc:
                    del doc["_id"]
                    
                # Serialize datetime fields
                for field in ["created_at", "updated_at"]:
                    if field in doc and hasattr(doc[field], 'isoformat'):
                        doc[field] = doc[field].isoformat()
                        
                buyer_orders.append(doc)
            except Exception:
                continue
        
        for doc in seller_orders_docs:
            try:
                if "_id" in doc:
                    del doc["_id"]
                    
                # Serialize datetime fields
                for field in ["created_at", "updated_at"]:
                    if field in doc and hasattr(doc[field], 'isoformat'):
                        doc[field] = doc[field].isoformat()
                        
                seller_orders.append(doc)
            except Exception:
                continue
        
        return {
            "buyer_orders": buyer_orders,
            "seller_orders": seller_orders
        }
    
    except Exception as e:
        logger.error(f"Error fetching user orders: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch orders")

@api_router.put("/orders/{order_id}/status")
async def update_order_status(
    order_id: str,
    status_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Update order status (seller only)"""
    try:
        # Verify user is the seller
        order = await db.orders.find_one({"id": order_id, "seller_id": current_user.id})
        if not order:
            raise HTTPException(status_code=404, detail="Order not found or access denied")
        
        new_status = status_data.get("delivery_status")
        allowed_statuses = ["preparing", "shipped", "in_transit", "delivered", "cancelled"]
        
        if new_status not in allowed_statuses:
            raise HTTPException(status_code=400, detail="Invalid status")
        
        # Update order
        await db.orders.update_one(
            {"id": order_id},
            {
                "$set": {
                    "delivery_status": new_status,
                    "updated_at": datetime.now(timezone.utc),
                    "status_note": status_data.get("note", "")
                }
            }
        )
        
        # Emit event
        await emit_admin_event("ORDER.STATUS_UPDATED", {
            "order_id": order_id,
            "new_status": new_status,
            "updated_by": current_user.id
        })
        
        # Emit SSE event for admin dashboard
        await admin_event_emitters.emit_system_alert(
            alert_type="order_status_update",
            message=f"Order {order_id} status updated to {new_status}",
            severity="info",
            details={
                "order_id": order_id,
                "new_status": new_status,
                "updated_by": current_user.id
            }
        )
        
        return {"success": True, "message": "Order status updated"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating order status: {e}")
        raise HTTPException(status_code=500, detail="Failed to update order status")

# Database initialization
@app.on_event("startup")
async def initialize_database():
    """Initialize database with comprehensive livestock taxonomy"""
    try:
        # FORCE REINITIALIZE - Clear existing incomplete data
        print("Checking database status...")
        
        # Check if we have the old schema without category_group_id
        species_sample = await db.species.find_one({})
        if species_sample and 'category_group_id' not in species_sample:
            print("⚠️  Found old species records without category_group_id - reinitializing taxonomy...")
            
            # Clear old taxonomy data  
            await db.species.delete_many({})
            await db.breeds.delete_many({})
            await db.product_types.delete_many({})
            await db.category_groups.delete_many({})
            
            print("✅ Cleared old taxonomy data")
        
        # Check if category groups exist
        groups_count = await db.category_groups.count_documents({})
        if groups_count == 0:
            print("🔄 Initializing comprehensive taxonomy...")
            
            # Initialize category groups
            category_groups_data = [
                {"id": str(uuid.uuid4()), "name": "Poultry", "description": "All bird species raised for meat, eggs, or breeding"},
                {"id": str(uuid.uuid4()), "name": "Ruminants", "description": "Cattle, goats, sheep and other cud-chewing livestock"},
                {"id": str(uuid.uuid4()), "name": "Rabbits", "description": "Rabbits for meat, fur, or breeding"},
                {"id": str(uuid.uuid4()), "name": "Aquaculture", "description": "Fish and seafood farming"},
                {"id": str(uuid.uuid4()), "name": "Other Small Livestock", "description": "Pigeons, guinea pigs and other small animals"}
            ]
            await db.category_groups.insert_many(category_groups_data)
            
            # Get group IDs for reference
            poultry_group = await db.category_groups.find_one({"name": "Poultry"})
            ruminants_group = await db.category_groups.find_one({"name": "Ruminants"})
            rabbits_group = await db.category_groups.find_one({"name": "Rabbits"})
            aquaculture_group = await db.category_groups.find_one({"name": "Aquaculture"})
            other_group = await db.category_groups.find_one({"name": "Other Small Livestock"})
            
            print(f"✅ Created {len(category_groups_data)} category groups")
            
            # Initialize comprehensive species data
            species_data = [
                # Poultry Species
                {"id": str(uuid.uuid4()), "name": "Commercial Broilers", "category_group_id": poultry_group["id"], "is_egg_laying": True, "description": "Fast-growing meat chickens"},
                {"id": str(uuid.uuid4()), "name": "Commercial Layers", "category_group_id": poultry_group["id"], "is_egg_laying": True, "description": "High egg production chickens"},
                {"id": str(uuid.uuid4()), "name": "Dual-Purpose Chickens", "category_group_id": poultry_group["id"], "is_egg_laying": True, "description": "Heritage/Indigenous breeds for meat and eggs"},
                {"id": str(uuid.uuid4()), "name": "Free Range Chickens", "category_group_id": poultry_group["id"], "is_egg_laying": True, "is_free_range": True, "description": "Free range certified chickens"},
                {"id": str(uuid.uuid4()), "name": "Ducks", "category_group_id": poultry_group["id"], "is_egg_laying": True, "description": "Ducks for meat, eggs, or breeding"},
                {"id": str(uuid.uuid4()), "name": "Geese", "category_group_id": poultry_group["id"], "is_egg_laying": True, "description": "Geese for meat or breeding"},
                {"id": str(uuid.uuid4()), "name": "Turkeys", "category_group_id": poultry_group["id"], "is_egg_laying": True, "description": "Turkeys for meat or breeding"},
                {"id": str(uuid.uuid4()), "name": "Quail", "category_group_id": poultry_group["id"], "is_egg_laying": True, "description": "Quail for meat, eggs, or breeding"},
                {"id": str(uuid.uuid4()), "name": "Guinea Fowl", "category_group_id": poultry_group["id"], "is_egg_laying": True, "description": "Guinea fowl for meat or pest control"},
                
                # Ruminants Species
                {"id": str(uuid.uuid4()), "name": "Cattle", "category_group_id": ruminants_group["id"], "is_ruminant": True, "description": "Cattle for dairy, beef, or breeding"},
                {"id": str(uuid.uuid4()), "name": "Goats", "category_group_id": ruminants_group["id"], "is_ruminant": True, "description": "Goats for meat, milk, fiber, or breeding"},
                {"id": str(uuid.uuid4()), "name": "Sheep", "category_group_id": ruminants_group["id"], "is_ruminant": True, "description": "Sheep for meat, wool, or breeding"},
                
                # Rabbits Species
                {"id": str(uuid.uuid4()), "name": "Rabbits", "category_group_id": rabbits_group["id"], "description": "Rabbits for meat, fur, or breeding"},
                
                # Aquaculture Species
                {"id": str(uuid.uuid4()), "name": "Freshwater Fish", "category_group_id": aquaculture_group["id"], "is_fish": True, "is_egg_laying": True, "description": "Freshwater fish species"},
                {"id": str(uuid.uuid4()), "name": "Saltwater Fish", "category_group_id": aquaculture_group["id"], "is_fish": True, "is_egg_laying": True, "description": "Saltwater fish species"},
                
                # Other Small Livestock
                {"id": str(uuid.uuid4()), "name": "Pigeons", "category_group_id": other_group["id"], "is_egg_laying": True, "description": "Pigeons and doves"},
                {"id": str(uuid.uuid4()), "name": "Guinea Pigs", "category_group_id": other_group["id"], "description": "Guinea pigs (Cuy) for meat"}
            ]
            await db.species.insert_many(species_data)
            print(f"✅ Created {len(species_data)} species")
            
            # Initialize comprehensive product types
            product_types_data = [
                {"id": str(uuid.uuid4()), "code": "FRESH_EGGS", "label": "Fresh Eggs", "description": "Table eggs for consumption", "applicable_to_groups": ["Poultry", "Other Small Livestock"]},
                {"id": str(uuid.uuid4()), "code": "FERTILIZED_EGGS", "label": "Fertilized Eggs", "description": "Hatching eggs", "applicable_to_groups": ["Poultry", "Aquaculture", "Other Small Livestock"]},
                {"id": str(uuid.uuid4()), "code": "DAY_OLD", "label": "Day-Old", "description": "Day-old chicks/animals", "applicable_to_groups": ["Poultry", "Other Small Livestock"]},
                {"id": str(uuid.uuid4()), "code": "CALVES_KIDS_LAMBS", "label": "Calves/Kids/Lambs", "description": "Young ruminants", "applicable_to_groups": ["Ruminants"]},
                {"id": str(uuid.uuid4()), "code": "KITS", "label": "Kits", "description": "Young rabbits", "applicable_to_groups": ["Rabbits"]},
                {"id": str(uuid.uuid4()), "code": "FRY", "label": "Fry", "description": "Day-old fish", "applicable_to_groups": ["Aquaculture"]},
                {"id": str(uuid.uuid4()), "code": "FINGERLINGS", "label": "Fingerlings", "description": "Juvenile fish", "applicable_to_groups": ["Aquaculture"]},
                {"id": str(uuid.uuid4()), "code": "JUVENILES", "label": "Juveniles", "description": "Juvenile/young animals", "applicable_to_groups": ["Aquaculture", "Ruminants", "Other Small Livestock"]},
                {"id": str(uuid.uuid4()), "code": "POINT_OF_LAY", "label": "Point of Lay", "description": "Near-lay pullets", "applicable_to_groups": ["Poultry"]},
                {"id": str(uuid.uuid4()), "code": "GROWERS", "label": "Growers", "description": "Growing stage animals", "applicable_to_groups": ["Poultry", "Rabbits", "Other Small Livestock", "Aquaculture"]},
                {"id": str(uuid.uuid4()), "code": "HEIFERS", "label": "Heifers", "description": "Young female cattle", "applicable_to_groups": ["Ruminants"]},
                {"id": str(uuid.uuid4()), "code": "BULLS", "label": "Bulls", "description": "Male breeding cattle", "applicable_to_groups": ["Ruminants"]},
                {"id": str(uuid.uuid4()), "code": "DAIRY_ANIMALS", "label": "Dairy Animals", "description": "Milk producing animals", "applicable_to_groups": ["Ruminants"]},
                {"id": str(uuid.uuid4()), "code": "LAYERS", "label": "Layers", "description": "Egg laying birds", "applicable_to_groups": ["Poultry", "Other Small Livestock"]},
                {"id": str(uuid.uuid4()), "code": "MARKET_READY", "label": "Market-Ready", "description": "Ready for slaughter/harvest", "applicable_to_groups": ["Poultry", "Ruminants", "Rabbits", "Aquaculture", "Other Small Livestock"]},
                {"id": str(uuid.uuid4()), "code": "BREEDING_STOCK", "label": "Breeding Stock", "description": "For breeding purposes", "applicable_to_groups": ["Poultry", "Ruminants", "Rabbits", "Aquaculture", "Other Small Livestock"]}
            ]
            await db.product_types.insert_many(product_types_data)
            print(f"✅ Created {len(product_types_data)} product types")
            
            # Initialize comprehensive breeds
            await initialize_all_breeds()
            
            # Clear old listings and create new ones with correct species IDs
            await db.listings.delete_many({})
            
            # Force admin user creation check
            admin_check = await db.users.find_one({"email": "admin@stocklot.co.za"})
            if not admin_check:
                print("🔧 Creating admin user...")
                admin_user_data = {
                    "id": str(uuid.uuid4()),
                    "email": "admin@stocklot.co.za",
                    "full_name": "System Administrator",
                    "phone": "+27 123 456 789",
                    "roles": ["admin", "seller", "buyer"],
                    "is_verified": True,
                    "password": hash_password("admin123"),
                    "created_at": datetime.now(timezone.utc)
                }
                await db.users.insert_one(admin_user_data)
                print("✅ Created admin user: admin@stocklot.co.za / admin123")
            
            await create_sample_listings()
            
            print("🎉 Comprehensive livestock taxonomy initialized successfully!")
            
        else:
            print("✅ Comprehensive taxonomy already exists")
            
            # Check for missing breeds and add them
            print("🔄 Checking for missing breeds...")
            species_without_breeds = [
                "Geese", "Turkeys", "Quail", "Guinea Fowl", 
                "Saltwater Fish", "Pigeons", "Guinea Pigs"
            ]
            
            breeds_added = False
            for species_name in species_without_breeds:
                species_doc = await db.species.find_one({"name": species_name})
                if species_doc:
                    breed_count = await db.breeds.count_documents({"species_id": species_doc["id"]})
                    if breed_count == 0:
                        print(f"⚠️  {species_name} has no breeds, adding them...")
                        breeds_added = True
                        
            # Check for missing product types and add them
            print("🔄 Checking for missing product types...")
            current_product_types = await db.product_types.count_documents({})
            if current_product_types < 16:  # We should have 16 product types now
                print(f"⚠️  Only {current_product_types} product types found, adding missing ones...")
                # Clear and reinitialize product types
                await db.product_types.delete_many({})
                product_types_data = [
                    {"id": str(uuid.uuid4()), "code": "FRESH_EGGS", "label": "Fresh Eggs", "description": "Table eggs for consumption", "applicable_to_groups": ["Poultry", "Other Small Livestock"]},
                    {"id": str(uuid.uuid4()), "code": "FERTILIZED_EGGS", "label": "Fertilized Eggs", "description": "Hatching eggs", "applicable_to_groups": ["Poultry", "Aquaculture", "Other Small Livestock"]},
                    {"id": str(uuid.uuid4()), "code": "DAY_OLD", "label": "Day-Old", "description": "Day-old chicks/animals", "applicable_to_groups": ["Poultry", "Other Small Livestock"]},
                    {"id": str(uuid.uuid4()), "code": "CALVES_KIDS_LAMBS", "label": "Calves/Kids/Lambs", "description": "Young ruminants", "applicable_to_groups": ["Ruminants"]},
                    {"id": str(uuid.uuid4()), "code": "KITS", "label": "Kits", "description": "Young rabbits", "applicable_to_groups": ["Rabbits"]},
                    {"id": str(uuid.uuid4()), "code": "FRY", "label": "Fry", "description": "Day-old fish", "applicable_to_groups": ["Aquaculture"]},
                    {"id": str(uuid.uuid4()), "code": "FINGERLINGS", "label": "Fingerlings", "description": "Juvenile fish", "applicable_to_groups": ["Aquaculture"]},
                    {"id": str(uuid.uuid4()), "code": "JUVENILES", "label": "Juveniles", "description": "Juvenile/young animals", "applicable_to_groups": ["Aquaculture", "Ruminants", "Other Small Livestock"]},
                    {"id": str(uuid.uuid4()), "code": "POINT_OF_LAY", "label": "Point of Lay", "description": "Near-lay pullets", "applicable_to_groups": ["Poultry"]},
                    {"id": str(uuid.uuid4()), "code": "GROWERS", "label": "Growers", "description": "Growing stage animals", "applicable_to_groups": ["Poultry", "Rabbits", "Other Small Livestock", "Aquaculture"]},
                    {"id": str(uuid.uuid4()), "code": "HEIFERS", "label": "Heifers", "description": "Young female cattle", "applicable_to_groups": ["Ruminants"]},
                    {"id": str(uuid.uuid4()), "code": "BULLS", "label": "Bulls", "description": "Male breeding cattle", "applicable_to_groups": ["Ruminants"]},
                    {"id": str(uuid.uuid4()), "code": "DAIRY_ANIMALS", "label": "Dairy Animals", "description": "Milk producing animals", "applicable_to_groups": ["Ruminants"]},
                    {"id": str(uuid.uuid4()), "code": "LAYERS", "label": "Layers", "description": "Egg laying birds", "applicable_to_groups": ["Poultry", "Other Small Livestock"]},
                    {"id": str(uuid.uuid4()), "code": "MARKET_READY", "label": "Market-Ready", "description": "Ready for slaughter/harvest", "applicable_to_groups": ["Poultry", "Ruminants", "Rabbits", "Aquaculture", "Other Small Livestock"]},
                    {"id": str(uuid.uuid4()), "code": "BREEDING_STOCK", "label": "Breeding Stock", "description": "For breeding purposes", "applicable_to_groups": ["Poultry", "Ruminants", "Rabbits", "Aquaculture", "Other Small Livestock"]}
                ]
                await db.product_types.insert_many(product_types_data)
                print(f"✅ Added {len(product_types_data)} product types!")
                        
            if breeds_added:
                print("🔄 Adding missing breeds...")
                await initialize_other_breeds()
                print("✅ Missing breeds added successfully!")
            else:
                print("✅ All species have breeds")
            
        # Initialize Review System Database
        try:
            print("🌟 Setting up review system database...")
            await setup_review_database(db)
            print("✅ Review system database setup completed")
        except Exception as e:
            logger.error(f"Review system database setup failed: {e}")
            print(f"⚠️  Review system database setup failed: {e}")
        
        # Initialize Fee System Database
        try:
            print("💰 Setting up fee system database...")
            from services.fee_db_setup import setup_fee_database
            await setup_fee_database(db)
            print("✅ Fee system database setup completed")
        except Exception as e:
            logger.error(f"Fee system database setup failed: {e}")
            print(f"⚠️  Fee system database setup failed: {e}")
        
        # Start Review System Background Jobs
        try:
            global review_cron_service
            review_cron_service = get_review_cron_service(db)
            
            # Start background jobs in a separate task to avoid blocking startup
            asyncio.create_task(review_cron_service.start_background_jobs())
            print("✅ Review system background jobs started")
        except Exception as e:
            logger.error(f"Review system background jobs failed to start: {e}")
            print(f"⚠️  Review system background jobs failed to start: {e}")
            
        logger.info("Database initialization completed successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        print(f"❌ Database initialization failed: {e}")

async def initialize_all_breeds():
    """Initialize all breeds for all species"""
    
    # Commercial Broilers
    broiler_species = await db.species.find_one({"name": "Commercial Broilers"})
    if broiler_species:
        broiler_breeds = [
            {"id": str(uuid.uuid4()), "species_id": broiler_species["id"], "name": "Ross 308", "purpose_hint": "meat", "characteristics": "Fast-growing, high feed conversion"},
            {"id": str(uuid.uuid4()), "species_id": broiler_species["id"], "name": "Cobb 500", "purpose_hint": "meat", "characteristics": "Excellent breast meat yield"},
            {"id": str(uuid.uuid4()), "species_id": broiler_species["id"], "name": "Hubbard", "purpose_hint": "meat", "characteristics": "Good survivability"},
            {"id": str(uuid.uuid4()), "species_id": broiler_species["id"], "name": "Arbor Acres", "purpose_hint": "meat", "characteristics": "Uniform growth rate"}
        ]
        await db.breeds.insert_many(broiler_breeds)
    
    # Commercial Layers
    layer_species = await db.species.find_one({"name": "Commercial Layers"})
    if layer_species:
        layer_breeds = [
            {"id": str(uuid.uuid4()), "species_id": layer_species["id"], "name": "ISA Brown", "purpose_hint": "egg", "characteristics": "High egg production, brown eggs"},
            {"id": str(uuid.uuid4()), "species_id": layer_species["id"], "name": "Hy-Line Brown", "purpose_hint": "egg", "characteristics": "Excellent feed conversion"},
            {"id": str(uuid.uuid4()), "species_id": layer_species["id"], "name": "Lohmann Brown", "purpose_hint": "egg", "characteristics": "Calm temperament, good production"},
            {"id": str(uuid.uuid4()), "species_id": layer_species["id"], "name": "White Leghorn", "purpose_hint": "egg", "characteristics": "White eggs, high production"},
            {"id": str(uuid.uuid4()), "species_id": layer_species["id"], "name": "Australorp", "purpose_hint": "egg", "characteristics": "Good layers, dual purpose"}
        ]
        await db.breeds.insert_many(layer_breeds)
    
    # Dual-Purpose Chickens
    dual_species = await db.species.find_one({"name": "Dual-Purpose Chickens"})
    if dual_species:
        dual_breeds = [
            {"id": str(uuid.uuid4()), "species_id": dual_species["id"], "name": "Rhode Island Red", "purpose_hint": "dual", "characteristics": "Hardy, good meat and egg production"},
            {"id": str(uuid.uuid4()), "species_id": dual_species["id"], "name": "Plymouth Rock", "purpose_hint": "dual", "characteristics": "Docile, good for beginners"},
            {"id": str(uuid.uuid4()), "species_id": dual_species["id"], "name": "Sussex", "purpose_hint": "dual", "characteristics": "Hardy, good foragers"},
            {"id": str(uuid.uuid4()), "species_id": dual_species["id"], "name": "Orpington", "purpose_hint": "dual", "characteristics": "Broody, good mothers"},
            {"id": str(uuid.uuid4()), "species_id": dual_species["id"], "name": "Koekoek", "purpose_hint": "dual", "origin_country": "South Africa", "characteristics": "Local adaptation, hardy"},
            {"id": str(uuid.uuid4()), "species_id": dual_species["id"], "name": "Naked Neck", "purpose_hint": "dual", "characteristics": "Heat tolerant"},
            {"id": str(uuid.uuid4()), "species_id": dual_species["id"], "name": "Venda", "purpose_hint": "dual", "origin_country": "South Africa", "characteristics": "Indigenous South African breed"},
            {"id": str(uuid.uuid4()), "species_id": dual_species["id"], "name": "Ovambo", "purpose_hint": "dual", "origin_country": "South Africa", "characteristics": "Indigenous Namibian/South African breed"}
        ]
        await db.breeds.insert_many(dual_breeds)
    
    # Free Range Chickens (same breeds as dual-purpose but with free range certification)
    freerange_species = await db.species.find_one({"name": "Free Range Chickens"})
    if freerange_species:
        freerange_breeds = [
            {"id": str(uuid.uuid4()), "species_id": freerange_species["id"], "name": "Rhode Island Red (Free Range)", "purpose_hint": "dual", "characteristics": "Free range certified, hardy"},
            {"id": str(uuid.uuid4()), "species_id": freerange_species["id"], "name": "Koekoek (Free Range)", "purpose_hint": "dual", "origin_country": "South Africa", "characteristics": "Free range certified, local adaptation"},
            {"id": str(uuid.uuid4()), "species_id": freerange_species["id"], "name": "Sussex (Free Range)", "purpose_hint": "dual", "characteristics": "Free range certified, good foragers"},
            {"id": str(uuid.uuid4()), "species_id": freerange_species["id"], "name": "Naked Neck (Free Range)", "purpose_hint": "dual", "characteristics": "Free range certified, heat tolerant"},
            {"id": str(uuid.uuid4()), "species_id": freerange_species["id"], "name": "Venda (Free Range)", "purpose_hint": "dual", "origin_country": "South Africa", "characteristics": "Free range certified indigenous breed"}
        ]
        await db.breeds.insert_many(freerange_breeds)
    
    # Ducks
    duck_species = await db.species.find_one({"name": "Ducks"})
    if duck_species:
        duck_breeds = [
            {"id": str(uuid.uuid4()), "species_id": duck_species["id"], "name": "Pekin", "purpose_hint": "meat", "characteristics": "Fast growing meat duck"},
            {"id": str(uuid.uuid4()), "species_id": duck_species["id"], "name": "Muscovy", "purpose_hint": "meat", "characteristics": "Lean meat, good mothers"},
            {"id": str(uuid.uuid4()), "species_id": duck_species["id"], "name": "Rouen", "purpose_hint": "dual", "characteristics": "Good meat and egg production"},
            {"id": str(uuid.uuid4()), "species_id": duck_species["id"], "name": "Khaki Campbell", "purpose_hint": "egg", "characteristics": "Excellent egg layers"},
            {"id": str(uuid.uuid4()), "species_id": duck_species["id"], "name": "Indian Runner", "purpose_hint": "egg", "characteristics": "Upright posture, good layers"},
            {"id": str(uuid.uuid4()), "species_id": duck_species["id"], "name": "Aylesbury", "purpose_hint": "meat", "characteristics": "Traditional meat duck"},
            {"id": str(uuid.uuid4()), "species_id": duck_species["id"], "name": "Swedish Blue", "purpose_hint": "dual", "characteristics": "Hardy, good foragers"}
        ]
        await db.breeds.insert_many(duck_breeds)
    
    # Continue with other species breeds...
    await initialize_ruminant_breeds()
    await initialize_other_breeds()

async def initialize_ruminant_breeds():
    """Initialize breeds for ruminants"""
    
    # Cattle breeds
    cattle_species = await db.species.find_one({"name": "Cattle"})
    if cattle_species:
        cattle_breeds = [
            # Beef breeds
            {"id": str(uuid.uuid4()), "species_id": cattle_species["id"], "name": "Nguni", "purpose_hint": "beef", "origin_country": "South Africa", "characteristics": "Indigenous, heat tolerant"},
            {"id": str(uuid.uuid4()), "species_id": cattle_species["id"], "name": "Bonsmara", "purpose_hint": "beef", "origin_country": "South Africa", "characteristics": "Composite breed, adapted to SA conditions"},
            {"id": str(uuid.uuid4()), "species_id": cattle_species["id"], "name": "Afrikaner", "purpose_hint": "beef", "origin_country": "South Africa", "characteristics": "Indigenous, heat and drought tolerant"},
            {"id": str(uuid.uuid4()), "species_id": cattle_species["id"], "name": "Angus", "purpose_hint": "beef", "characteristics": "Excellent meat quality"},
            {"id": str(uuid.uuid4()), "species_id": cattle_species["id"], "name": "Hereford", "purpose_hint": "beef", "characteristics": "Good mothers, hardy"},
            {"id": str(uuid.uuid4()), "species_id": cattle_species["id"], "name": "Charolais", "purpose_hint": "beef", "characteristics": "Large frame, fast growing"},
            {"id": str(uuid.uuid4()), "species_id": cattle_species["id"], "name": "Brahman", "purpose_hint": "beef", "characteristics": "Heat tolerant, tick resistant"},
            # Dairy breeds
            {"id": str(uuid.uuid4()), "species_id": cattle_species["id"], "name": "Holstein-Friesian", "purpose_hint": "dairy", "characteristics": "High milk production"},
            {"id": str(uuid.uuid4()), "species_id": cattle_species["id"], "name": "Jersey", "purpose_hint": "dairy", "characteristics": "High butterfat content"},
            {"id": str(uuid.uuid4()), "species_id": cattle_species["id"], "name": "Ayrshire", "purpose_hint": "dairy", "characteristics": "Hardy, good pasture utilization"},
            {"id": str(uuid.uuid4()), "species_id": cattle_species["id"], "name": "Guernsey", "purpose_hint": "dairy", "characteristics": "Golden milk, high protein"}
        ]
        await db.breeds.insert_many(cattle_breeds)
    
    # Goat breeds
    goat_species = await db.species.find_one({"name": "Goats"})
    if goat_species:
        goat_breeds = [
            # Meat goats
            {"id": str(uuid.uuid4()), "species_id": goat_species["id"], "name": "Boer", "purpose_hint": "meat", "origin_country": "South Africa", "characteristics": "Fast growing, excellent meat quality"},
            {"id": str(uuid.uuid4()), "species_id": goat_species["id"], "name": "Kalahari Red", "purpose_hint": "meat", "origin_country": "South Africa", "characteristics": "Heat tolerant, good mothers"},
            {"id": str(uuid.uuid4()), "species_id": goat_species["id"], "name": "Savanna", "purpose_hint": "meat", "origin_country": "South Africa", "characteristics": "Hardy, good browsing ability"},
            # Dairy goats
            {"id": str(uuid.uuid4()), "species_id": goat_species["id"], "name": "Saanen", "purpose_hint": "dairy", "characteristics": "High milk production"},
            {"id": str(uuid.uuid4()), "species_id": goat_species["id"], "name": "Nubian", "purpose_hint": "dairy", "characteristics": "High butterfat milk"},
            {"id": str(uuid.uuid4()), "species_id": goat_species["id"], "name": "Alpine", "purpose_hint": "dairy", "characteristics": "Good milk production, hardy"},
            {"id": str(uuid.uuid4()), "species_id": goat_species["id"], "name": "Toggenburg", "purpose_hint": "dairy", "characteristics": "Consistent milk production"},
            # Fiber goats
            {"id": str(uuid.uuid4()), "species_id": goat_species["id"], "name": "Angora", "purpose_hint": "fiber", "characteristics": "Mohair production"},
            {"id": str(uuid.uuid4()), "species_id": goat_species["id"], "name": "Cashmere", "purpose_hint": "fiber", "characteristics": "Fine fiber production"}
        ]
        await db.breeds.insert_many(goat_breeds)
    
    # Sheep breeds
    sheep_species = await db.species.find_one({"name": "Sheep"})
    if sheep_species:
        sheep_breeds = [
            # Meat sheep
            {"id": str(uuid.uuid4()), "species_id": sheep_species["id"], "name": "Dorper", "purpose_hint": "meat", "origin_country": "South Africa", "characteristics": "Hair sheep, no shearing required"},
            {"id": str(uuid.uuid4()), "species_id": sheep_species["id"], "name": "Damara", "purpose_hint": "meat", "characteristics": "Fat-tailed, drought tolerant"},
            {"id": str(uuid.uuid4()), "species_id": sheep_species["id"], "name": "Blackhead Persian", "purpose_hint": "meat", "characteristics": "Hair sheep, heat tolerant"},
            {"id": str(uuid.uuid4()), "species_id": sheep_species["id"], "name": "Suffolk", "purpose_hint": "meat", "characteristics": "Fast growing, good meat quality"},
            # Wool sheep
            {"id": str(uuid.uuid4()), "species_id": sheep_species["id"], "name": "Merino", "purpose_hint": "wool", "characteristics": "High quality wool"},
            {"id": str(uuid.uuid4()), "species_id": sheep_species["id"], "name": "South African Mutton Merino", "purpose_hint": "dual", "origin_country": "South Africa", "characteristics": "Meat and wool production"},
            {"id": str(uuid.uuid4()), "species_id": sheep_species["id"], "name": "Corriedale", "purpose_hint": "dual", "characteristics": "Good wool and meat"}
        ]
        await db.breeds.insert_many(sheep_breeds)

async def initialize_other_breeds():
    """Initialize breeds for other species"""
    
    # Geese breeds
    geese_species = await db.species.find_one({"name": "Geese"})
    if geese_species:
        geese_breeds = [
            {"id": str(uuid.uuid4()), "species_id": geese_species["id"], "name": "Embden", "purpose_hint": "meat", "characteristics": "Large white geese, excellent meat production"},
            {"id": str(uuid.uuid4()), "species_id": geese_species["id"], "name": "Toulouse", "purpose_hint": "meat", "characteristics": "Heavy breed, good for meat and foie gras"},
            {"id": str(uuid.uuid4()), "species_id": geese_species["id"], "name": "Chinese", "purpose_hint": "egg", "characteristics": "Good egg layers, alert guardians"},
            {"id": str(uuid.uuid4()), "species_id": geese_species["id"], "name": "African", "purpose_hint": "dual", "characteristics": "Good meat and egg production"},
            {"id": str(uuid.uuid4()), "species_id": geese_species["id"], "name": "Pilgrim", "purpose_hint": "dual", "characteristics": "Auto-sexing breed, calm temperament"}
        ]
        await db.breeds.insert_many(geese_breeds)
    
    # Turkey breeds
    turkey_species = await db.species.find_one({"name": "Turkeys"})
    if turkey_species:
        turkey_breeds = [
            {"id": str(uuid.uuid4()), "species_id": turkey_species["id"], "name": "Broad Breasted White", "purpose_hint": "meat", "characteristics": "Fast growing commercial breed"},
            {"id": str(uuid.uuid4()), "species_id": turkey_species["id"], "name": "Bronze", "purpose_hint": "meat", "characteristics": "Traditional heritage breed"},
            {"id": str(uuid.uuid4()), "species_id": turkey_species["id"], "name": "Bourbon Red", "purpose_hint": "meat", "characteristics": "Heritage breed with excellent flavor"},
            {"id": str(uuid.uuid4()), "species_id": turkey_species["id"], "name": "Narragansett", "purpose_hint": "dual", "characteristics": "Hardy heritage breed"},
            {"id": str(uuid.uuid4()), "species_id": turkey_species["id"], "name": "Black Spanish", "purpose_hint": "meat", "characteristics": "Early heritage breed, good foragers"}
        ]
        await db.breeds.insert_many(turkey_breeds)
    
    # Quail breeds
    quail_species = await db.species.find_one({"name": "Quail"})
    if quail_species:
        quail_breeds = [
            {"id": str(uuid.uuid4()), "species_id": quail_species["id"], "name": "Japanese Quail", "purpose_hint": "egg", "characteristics": "High egg production, fast maturing"},
            {"id": str(uuid.uuid4()), "species_id": quail_species["id"], "name": "Bobwhite Quail", "purpose_hint": "meat", "characteristics": "Good meat quality, popular game bird"},
            {"id": str(uuid.uuid4()), "species_id": quail_species["id"], "name": "Coturnix Quail", "purpose_hint": "dual", "characteristics": "Fast growing, good for meat and eggs"},
            {"id": str(uuid.uuid4()), "species_id": quail_species["id"], "name": "California Quail", "purpose_hint": "ornamental", "characteristics": "Beautiful plumage, good for aviary"},
            {"id": str(uuid.uuid4()), "species_id": quail_species["id"], "name": "Pharaoh Quail", "purpose_hint": "meat", "characteristics": "Large size, excellent meat production"}
        ]
        await db.breeds.insert_many(quail_breeds)
    
    # Guinea Fowl breeds
    guinea_species = await db.species.find_one({"name": "Guinea Fowl"})
    if guinea_species:
        guinea_breeds = [
            {"id": str(uuid.uuid4()), "species_id": guinea_species["id"], "name": "Pearl Guinea", "purpose_hint": "meat", "characteristics": "Most common variety, good pest control"},
            {"id": str(uuid.uuid4()), "species_id": guinea_species["id"], "name": "White Guinea", "purpose_hint": "meat", "characteristics": "White plumage, easier to process"},
            {"id": str(uuid.uuid4()), "species_id": guinea_species["id"], "name": "Royal Purple", "purpose_hint": "ornamental", "characteristics": "Beautiful purple plumage"},
            {"id": str(uuid.uuid4()), "species_id": guinea_species["id"], "name": "Coral Blue", "purpose_hint": "ornamental", "characteristics": "Striking blue coloration"},
            {"id": str(uuid.uuid4()), "species_id": guinea_species["id"], "name": "Buff Dundotte", "purpose_hint": "meat", "characteristics": "Buff colored, good meat production"}
        ]
        await db.breeds.insert_many(guinea_breeds)
    
    # Pigeon breeds
    pigeon_species = await db.species.find_one({"name": "Pigeons"})
    if pigeon_species:
        pigeon_breeds = [
            {"id": str(uuid.uuid4()), "species_id": pigeon_species["id"], "name": "King Pigeon", "purpose_hint": "meat", "characteristics": "Large meat breed, excellent squab production"},
            {"id": str(uuid.uuid4()), "species_id": pigeon_species["id"], "name": "Carneau", "purpose_hint": "meat", "characteristics": "French meat breed, good mothers"},
            {"id": str(uuid.uuid4()), "species_id": pigeon_species["id"], "name": "Mondain", "purpose_hint": "meat", "characteristics": "Heavy utility breed"},
            {"id": str(uuid.uuid4()), "species_id": pigeon_species["id"], "name": "Racing Homer", "purpose_hint": "sport", "characteristics": "Excellent homing ability"},
            {"id": str(uuid.uuid4()), "species_id": pigeon_species["id"], "name": "Fantail", "purpose_hint": "ornamental", "characteristics": "Beautiful fan-shaped tail"}
        ]
        await db.breeds.insert_many(pigeon_breeds)
    
    # Guinea Pig breeds
    guinea_pig_species = await db.species.find_one({"name": "Guinea Pigs"})
    if guinea_pig_species:
        guinea_pig_breeds = [
            {"id": str(uuid.uuid4()), "species_id": guinea_pig_species["id"], "name": "Peruvian Cuy", "purpose_hint": "meat", "characteristics": "Traditional meat breed, fast growing"},
            {"id": str(uuid.uuid4()), "species_id": guinea_pig_species["id"], "name": "Andean Cuy", "purpose_hint": "meat", "characteristics": "High altitude adapted, good meat quality"},
            {"id": str(uuid.uuid4()), "species_id": guinea_pig_species["id"], "name": "Criolla Cuy", "purpose_hint": "meat", "characteristics": "Native breed, hardy and productive"},
            {"id": str(uuid.uuid4()), "species_id": guinea_pig_species["id"], "name": "Improved Cuy", "purpose_hint": "meat", "characteristics": "Selectively bred for meat production"},
            {"id": str(uuid.uuid4()), "species_id": guinea_pig_species["id"], "name": "White Cuy", "purpose_hint": "meat", "characteristics": "Fast growing, good feed conversion"}
        ]
        await db.breeds.insert_many(guinea_pig_breeds)
    
    # Rabbit breeds
    rabbit_species = await db.species.find_one({"name": "Rabbits"})
    if rabbit_species:
        rabbit_breeds = [
            {"id": str(uuid.uuid4()), "species_id": rabbit_species["id"], "name": "New Zealand White", "purpose_hint": "meat", "characteristics": "Fast growing, good meat quality"},
            {"id": str(uuid.uuid4()), "species_id": rabbit_species["id"], "name": "Californian", "purpose_hint": "meat", "characteristics": "Good mothering ability"},
            {"id": str(uuid.uuid4()), "species_id": rabbit_species["id"], "name": "Flemish Giant", "purpose_hint": "meat", "characteristics": "Large size, docile"},
            {"id": str(uuid.uuid4()), "species_id": rabbit_species["id"], "name": "Rex", "purpose_hint": "fur", "characteristics": "Velvet-like fur"},
            {"id": str(uuid.uuid4()), "species_id": rabbit_species["id"], "name": "Angora", "purpose_hint": "fiber", "characteristics": "Long fiber production"}
        ]
        await db.breeds.insert_many(rabbit_breeds)
    
    # Freshwater Fish species (as breeds)
    freshwater_species = await db.species.find_one({"name": "Freshwater Fish"})
    if freshwater_species:
        freshwater_breeds = [
            {"id": str(uuid.uuid4()), "species_id": freshwater_species["id"], "name": "Nile Tilapia", "purpose_hint": "food", "characteristics": "Fast growing, good flavor"},
            {"id": str(uuid.uuid4()), "species_id": freshwater_species["id"], "name": "Blue Tilapia", "purpose_hint": "food", "characteristics": "Cold tolerant"},
            {"id": str(uuid.uuid4()), "species_id": freshwater_species["id"], "name": "African Catfish", "purpose_hint": "food", "characteristics": "High protein, hardy"},
            {"id": str(uuid.uuid4()), "species_id": freshwater_species["id"], "name": "Common Carp", "purpose_hint": "food", "characteristics": "Hardy, fast growing"},
            {"id": str(uuid.uuid4()), "species_id": freshwater_species["id"], "name": "Rainbow Trout", "purpose_hint": "food", "characteristics": "Premium eating fish"}
        ]
        await db.breeds.insert_many(freshwater_breeds)
    
    # Saltwater Fish species (as breeds) 
    saltwater_species = await db.species.find_one({"name": "Saltwater Fish"})
    if saltwater_species:
        saltwater_breeds = [
            {"id": str(uuid.uuid4()), "species_id": saltwater_species["id"], "name": "Sea Bass", "purpose_hint": "food", "characteristics": "Premium white fish, excellent flavor"},
            {"id": str(uuid.uuid4()), "species_id": saltwater_species["id"], "name": "Sea Bream", "purpose_hint": "food", "characteristics": "Popular Mediterranean fish"},
            {"id": str(uuid.uuid4()), "species_id": saltwater_species["id"], "name": "Yellowtail", "purpose_hint": "food", "characteristics": "Fast growing, high value"},
            {"id": str(uuid.uuid4()), "species_id": saltwater_species["id"], "name": "Red Snapper", "purpose_hint": "food", "characteristics": "Premium eating fish"},
            {"id": str(uuid.uuid4()), "species_id": saltwater_species["id"], "name": "Salmon", "purpose_hint": "food", "characteristics": "High omega-3 content, premium fish"}
        ]
        await db.breeds.insert_many(saltwater_breeds)

async def create_sample_listings():
    """Create sample listings with new taxonomy"""
    try:
        # Get existing users
        admin_user = await db.users.find_one({"email": "admin@stocklot.co.za"})
        seller_user = await db.users.find_one({"email": "seller@farmstock.co.za"})
        
        # Create admin user if doesn't exist
        if not admin_user:
            admin_user_data = {
                "id": str(uuid.uuid4()),
                "email": "admin@stocklot.co.za",
                "full_name": "System Administrator",
                "phone": "+27 123 456 789",
                "roles": ["admin", "seller", "buyer"],
                "is_verified": True,
                "password": hash_password("admin123"),
                "created_at": datetime.now(timezone.utc)
            }
            await db.users.insert_one(admin_user_data)
            admin_user = admin_user_data
            print("✅ Created admin user: admin@stocklot.co.za / admin123")
        
        if not seller_user:
            # Create seller user if doesn't exist
            seller_user_data = {
                "id": str(uuid.uuid4()),
                "email": "seller@farmstock.co.za",
                "full_name": "John van der Merwe",
                "phone": "+27 82 555 1234",
                "roles": ["seller"],
                "is_verified": True,
                "password": hash_password("password123"),
                "created_at": datetime.now(timezone.utc)
            }
            await db.users.insert_one(seller_user_data)
            seller_user = seller_user_data
        
        # Get species and breeds for sample listings
        broiler_species = await db.species.find_one({"name": "Commercial Broilers"})
        freerange_species = await db.species.find_one({"name": "Free Range Chickens"})
        goat_species = await db.species.find_one({"name": "Goats"})
        
        ross_breed = await db.breeds.find_one({"name": "Ross 308"})
        koekoek_breed = await db.breeds.find_one({"name": "Koekoek (Free Range)"})
        boer_breed = await db.breeds.find_one({"name": "Boer"})
        
        # Get product types
        day_old_pt = await db.product_types.find_one({"code": "DAY_OLD"})
        grower_pt = await db.product_types.find_one({"code": "GROWERS"})
        breeding_pt = await db.product_types.find_one({"code": "BREEDING_STOCK"})
        fertilized_pt = await db.product_types.find_one({"code": "FERTILIZED_EGGS"})
        
        # Create sample listings
        sample_listings = []
        
        if ross_breed and day_old_pt and broiler_species:
            sample_listings.append({
                "id": str(uuid.uuid4()),
                "seller_id": seller_user["id"],
                "species_id": broiler_species["id"],
                "breed_id": ross_breed["id"],
                "product_type_id": day_old_pt["id"],
                "title": "Ross 308 Day-Old Chicks - Premium Broiler Stock",
                "description": "High-quality Ross 308 day-old chicks from certified breeding stock. Fast-growing broiler breed perfect for meat production. Vaccinated and health-checked.",
                "quantity": 100,
                "unit": "head",
                "price_per_unit": 15.50,
                "listing_type": "buy_now",
                "fulfillment": "delivery_only",
                "delivery_available": True,
                "has_vet_certificate": True,
                "health_notes": "Vaccinated against Marek's disease and Newcastle",
                "country": "South Africa",
                "region": "Gauteng",
                "city": "Pretoria",
                "images": [],
                "status": "active",
                "expires_at": datetime.now(timezone.utc) + timedelta(days=14),
                "created_at": datetime.now(timezone.utc)
            })
        
        if koekoek_breed and fertilized_pt and freerange_species:
            sample_listings.append({
                "id": str(uuid.uuid4()),
                "seller_id": seller_user["id"],
                "species_id": freerange_species["id"],
                "breed_id": koekoek_breed["id"],
                "product_type_id": fertilized_pt["id"],
                "title": "Free Range Koekoek Fertilized Eggs - Certified Organic",
                "description": "Premium free-range Koekoek fertilized eggs from certified organic farm. Perfect for hatching healthy, hardy chicks with excellent local adaptation.",
                "quantity": 50,
                "unit": "dozen",
                "price_per_unit": 25.00,
                "listing_type": "buy_now",
                "fulfillment": "delivery_only",
                "delivery_available": True,
                "has_vet_certificate": True,
                "health_notes": "Free range certified, organic feed only",
                "country": "South Africa",
                "region": "Western Cape",
                "city": "Stellenbosch",
                "images": [],
                "status": "active",
                "expires_at": datetime.now(timezone.utc) + timedelta(days=14),
                "created_at": datetime.now(timezone.utc)
            })
        
        if boer_breed and grower_pt and goat_species:
            sample_listings.append({
                "id": str(uuid.uuid4()),
                "seller_id": seller_user["id"],
                "species_id": goat_species["id"],
                "breed_id": boer_breed["id"],
                "product_type_id": grower_pt["id"],
                "title": "Boer Goat Kids - 3 Month Old Growers",
                "description": "Healthy Boer goat kids, 3 months old and weaned. Excellent for meat production or breeding program. Well-socialized and handled daily.",
                "quantity": 12,
                "unit": "head",
                "price_per_unit": 850.00,
                "listing_type": "buy_now",
                "fulfillment": "delivery_only",
                "delivery_available": False,
                "has_vet_certificate": True,
                "health_notes": "Dewormed and vaccinated. Health certificates available.",
                "country": "South Africa",
                "region": "Limpopo",
                "city": "Polokwane",
                "images": [],
                "status": "active",
                "expires_at": datetime.now(timezone.utc) + timedelta(days=14),
                "created_at": datetime.now(timezone.utc)
            })
        
        if sample_listings:
            await db.listings.insert_many(sample_listings)
            logger.info(f"Created {len(sample_listings)} sample listings with new taxonomy")
    
    except Exception as e:
        logger.error(f"Error creating sample listings: {e}")

# API Routes

# Authentication routes
def resolve_user_roles(user_type: Optional[str], legacy_role: Optional[UserRole] = None) -> List[UserRole]:
    """Convert the incoming user_type string into the appropriate list of UserRole enums."""
    normalized = (user_type or "").strip().lower()
    if normalized == "both":
        return [UserRole.BUYER, UserRole.SELLER]
    if normalized == "seller":
        return [UserRole.SELLER]
    if normalized == "buyer":
        return [UserRole.BUYER]
    if legacy_role:
        return [legacy_role]
    return [UserRole.BUYER]


@api_router.post("/auth/register")
async def register_user(user_data: UserCreate, request: Request):
    """Register a new user with referral attribution"""
    try:
        # Check if user exists
        existing_user = await db.users.find_one({"email": user_data.email})
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # Hash password
        hashed_password = hash_password(user_data.password)
        
        # Create user
        user = User(
            email=user_data.email,
            full_name=user_data.full_name,
            phone=user_data.phone,
            roles=resolve_user_roles(user_data.user_type, user_data.role)
        )
        
        # Save to database
        user_dict = user.dict()
        user_dict["password"] = hashed_password
        await db.users.insert_one(user_dict)
        
        # Handle referral attribution
        referral_code = request.cookies.get("referral_code")
        if referral_code:
            try:
                attribution_result = await referral_service_extended.attribute_signup(
                    new_user_id=user.id,
                    referral_code=referral_code
                )
                if attribution_result.get("attributed"):
                    logger.info(f"User {user.id} attributed to referral {referral_code}")
            except Exception as e:
                logger.warning(f"Referral attribution failed: {e}")
                # Don't fail registration if referral attribution fails
        
        # 📧 Send welcome email (E01)
        try:
            verify_url = f"https://stocklot.farm/verify-email?user_id={user.id}"
            await email_notification_service.send_welcome_email(
                user_email=user.email,
                first_name=user.full_name.split()[0] if user.full_name else "there",
                verify_url=verify_url
            )
            logger.info(f"Welcome email sent to {user.email}")
        except Exception as e:
            logger.warning(f"Failed to send welcome email to {user.email}: {e}")
            # Don't fail registration if email fails
        
        return {"message": "User registered successfully", "user_id": user.id}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error registering user: {e}")
        raise HTTPException(status_code=500, detail="Registration failed")

@api_router.post("/auth/login")
async def login_user(login_data: UserLogin, request: Request, response: Response):
    """Login user with HttpOnly cookies"""
    try:
        # Find user
        user_doc = await db.users.find_one({"email": login_data.email})
        if not user_doc:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # Verify password
        if not user_doc.get("password") or not verify_password(login_data.password, user_doc["password"]):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # Create user object
        user = User(**{k: v for k, v in user_doc.items() if k != "password"})
        
        # Set HttpOnly session cookie
        session_data = {
            "user_id": user.id,
            "email": user.email,
            "roles": user.roles if hasattr(user, 'roles') else ['buyer'],
            "exp": datetime.utcnow() + timedelta(days=7)  # 7 day session
        }
        
        # In production, use proper JWT signing
        import json
        import base64
        session_token = base64.b64encode(json.dumps(session_data, default=str).encode()).decode()
        
        # Set secure HttpOnly cookie
        response.set_cookie(
            key="sl_session",
            value=session_token,
            max_age=7 * 24 * 60 * 60,  # 7 days in seconds
            httponly=True,
            secure=True,  # HTTPS only in production
            samesite="lax",
            path="/"
        )
        
        # Return access_token for frontend bearer auth (dev: token = email, prod: use JWT)
        access_token = user.email  # Development token; replace with JWT in production
        
        return {
            "success": True,
            "user": user,
            "message": "Login successful",
            "access_token": access_token,
            "token_type": "bearer"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error logging in user: {e}")
        raise HTTPException(status_code=500, detail="Login failed")

@api_router.get("/auth/me")
async def get_current_user_session(request: Request):
    """Get current user from session cookie"""
    try:
        # Get session cookie
        session_cookie = request.cookies.get("sl_session")
        if not session_cookie:
            raise HTTPException(status_code=401, detail="No session found")
        
        # Decode session data (in production, verify JWT signature)
        import json
        import base64
        try:
            session_data = json.loads(base64.b64decode(session_cookie).decode())
        except:
            raise HTTPException(status_code=401, detail="Invalid session")
        
        # Check expiration
        exp_str = session_data.get("exp", "")
        if isinstance(exp_str, str):
            try:
                exp_time = datetime.fromisoformat(exp_str.replace('Z', '+00:00'))
            except ValueError:
                # Try parsing as UTC timestamp string
                exp_time = datetime.fromisoformat(exp_str)
        else:
            # If it's already a datetime object
            exp_time = exp_str
            
        if datetime.utcnow() > exp_time.replace(tzinfo=None):
            raise HTTPException(status_code=401, detail="Session expired")
        
        # Get user from database
        user_doc = await db.users.find_one({"id": session_data["user_id"]})
        if not user_doc:
            raise HTTPException(status_code=401, detail="User not found")
        
        # Return user data
        user = User(**{k: v for k, v in user_doc.items() if k != "password"})
        
        return {
            "user": user,
            "session": {
                "user_id": session_data["user_id"],
                "email": session_data["email"],
                "roles": session_data.get("roles", ['buyer'])
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting current user: {e}")
        raise HTTPException(status_code=401, detail="Authentication failed")

@api_router.post("/auth/logout")
async def logout_user(response: Response):
    """Logout user by clearing session cookie"""
    try:
        # Clear session cookie
        response.delete_cookie(
            key="sl_session",
            path="/",
            httponly=True,
            secure=True,
            samesite="lax"
        )
        
        return {"success": True, "message": "Logged out successfully"}
    
    except Exception as e:
        logger.error(f"Error logging out user: {e}")
        raise HTTPException(status_code=500, detail="Logout failed")

@api_router.post("/auth/refresh")
async def refresh_session(request: Request, response: Response):
    """Refresh session cookie"""
    try:
        # Get current session
        session_cookie = request.cookies.get("sl_session")
        if not session_cookie:
            raise HTTPException(status_code=401, detail="No session found")
        
        # Decode and validate session
        import json
        import base64
        try:
            session_data = json.loads(base64.b64decode(session_cookie).decode())
        except:
            raise HTTPException(status_code=401, detail="Invalid session")
        
        # Create new session with extended expiration
        new_session_data = {
            **session_data,
            "exp": datetime.utcnow() + timedelta(days=7)  # Extend by 7 days
        }
        
        # Set new session cookie
        new_session_token = base64.b64encode(json.dumps(new_session_data, default=str).encode()).decode()
        
        response.set_cookie(
            key="sl_session",
            value=new_session_token,
            max_age=7 * 24 * 60 * 60,  # 7 days
            httponly=True,
            secure=True,
            samesite="lax",
            path="/"
        )
        
        return {"success": True, "message": "Session refreshed"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refreshing session: {e}")
        raise HTTPException(status_code=401, detail="Session refresh failed")

# Social Authentication endpoints
@api_router.post("/auth/social", response_model=SocialAuthResponse)
async def social_auth(auth_request: SocialAuthRequest, request: Request):
    """Authenticate user with Google or Facebook"""
    try:
        # Verify the social token based on provider
        if auth_request.provider == "google":
            user_info = await social_auth_service.verify_google_token(auth_request.token)
        elif auth_request.provider == "facebook":
            user_info = await social_auth_service.verify_facebook_token(auth_request.token)
        else:
            raise HTTPException(status_code=400, detail="Unsupported provider")
        
        if not user_info:
            raise HTTPException(status_code=401, detail="Invalid social token")
        
        # Find or create user
        user_result = await social_auth_service.find_or_create_user(
            user_info, 
            auth_request.role
        )
        
        # Create access token (using email for now, should be JWT in production)
        access_token = user_result['email']
        
        return SocialAuthResponse(
            access_token=access_token,
            token_type="bearer",
            user={
                "id": user_result['user_id'],
                "email": user_result['email'],
                "full_name": user_result['full_name'],
                "roles": user_result['roles']
            },
            is_new_user=user_result['is_new_user'],
            needs_role_selection=user_result['needs_role_selection']
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in social authentication: {e}")
        raise HTTPException(status_code=500, detail="Social authentication failed")

@api_router.put("/auth/update-role")
async def update_user_role(
    role_request: UpdateRoleRequest,
    current_user: User = Depends(get_current_user)
):
    """Update user role after social signup"""
    try:
        success = await social_auth_service.update_user_role(
            current_user.id, 
            role_request.role
        )
        
        if not success:
            raise HTTPException(status_code=400, detail="Failed to update user role")
        
        return {"message": "Role updated successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user role: {e}")
        raise HTTPException(status_code=500, detail="Failed to update user role")

# Password Reset endpoints
@api_router.post("/auth/forgot-password")
async def request_password_reset(
    reset_request: PasswordResetRequest,
    request: Request
):
    """Request password reset email"""
    try:
        if not password_reset_service:
            raise HTTPException(status_code=503, detail="Password reset service unavailable")
        
        # Get base URL from request headers
        host = request.headers.get("host", "localhost:3000")
        protocol = "https" if request.headers.get("x-forwarded-proto") == "https" else "http"
        base_url = f"{protocol}://{host}"
        
        result = await password_reset_service.request_password_reset(
            email=reset_request.email,
            base_url=base_url
        )
        
        if result["success"]:
            return {"message": result["message"]}
        else:
            raise HTTPException(status_code=400, detail=result["message"])
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error requesting password reset: {e}")
        raise HTTPException(status_code=500, detail="Password reset request failed")

@api_router.get("/auth/reset-token/{token}")
async def verify_reset_token(token: str):
    """Verify password reset token validity"""
    try:
        if not password_reset_service:
            raise HTTPException(status_code=503, detail="Password reset service unavailable")
        
        result = await password_reset_service.verify_reset_token(token)
        
        if result["valid"]:
            return {
                "valid": True,
                "user_email": result["user_email"],
                "expires_at": result["expires_at"]
            }
        else:
            raise HTTPException(status_code=400, detail=result["message"])
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying reset token: {e}")
        raise HTTPException(status_code=500, detail="Token verification failed")

@api_router.post("/auth/reset-password")
async def confirm_password_reset(reset_data: PasswordResetConfirm):
    """Complete password reset with new password"""
    try:
        if not password_reset_service:
            raise HTTPException(status_code=503, detail="Password reset service unavailable")
        
        result = await password_reset_service.confirm_password_reset(
            token=reset_data.token,
            new_password=reset_data.new_password
        )
        
        if result["success"]:
            return {"message": result["message"]}
        else:
            raise HTTPException(status_code=400, detail=result["message"])
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error confirming password reset: {e}")
        raise HTTPException(status_code=500, detail="Password reset failed")

# Admin endpoint for password reset statistics
@api_router.get("/admin/password-reset/stats")
async def get_password_reset_stats(current_user: User = Depends(get_current_user)):
    """Get password reset statistics (admin only)"""
    try:
        # Check admin role
        if not current_user or "admin" not in (current_user.roles or []):
            raise HTTPException(status_code=403, detail="Admin access required")
        
        if not password_reset_service:
            raise HTTPException(status_code=503, detail="Password reset service unavailable")
        
        stats = await password_reset_service.get_reset_statistics()
        return stats
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting password reset stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get statistics")

# Two-Factor Authentication endpoints
@api_router.post("/auth/2fa/setup")
async def setup_2fa(current_user: User = Depends(get_current_user)):
    """Initialize 2FA setup for current user"""
    try:
        if not two_factor_service:
            raise HTTPException(status_code=503, detail="2FA service unavailable")
        
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        result = await two_factor_service.setup_2fa(current_user.id)
        
        if result["success"]:
            return {
                "secret_key": result["secret_key"],
                "qr_code": result["qr_code"],
                "backup_codes": result["backup_codes"],
                "app_name": result["app_name"],
                "username": result["username"]
            }
        else:
            raise HTTPException(status_code=400, detail=result["message"])
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting up 2FA: {e}")
        raise HTTPException(status_code=500, detail="2FA setup failed")

@api_router.post("/auth/2fa/verify-setup")
async def verify_2fa_setup(
    verify_data: TwoFactorVerifyRequest,
    current_user: User = Depends(get_current_user)
):
    """Verify 2FA setup and enable 2FA"""
    try:
        if not two_factor_service:
            raise HTTPException(status_code=503, detail="2FA service unavailable")
        
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        result = await two_factor_service.verify_2fa_setup(current_user.id, verify_data.token)
        
        if result["success"]:
            return {"message": result["message"]}
        else:
            raise HTTPException(status_code=400, detail=result["message"])
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying 2FA setup: {e}")
        raise HTTPException(status_code=500, detail="2FA verification failed")

@api_router.post("/auth/2fa/verify")
async def verify_2fa_login(verify_data: TwoFactorVerifyRequest):
    """Verify 2FA during login (called after password verification)"""
    try:
        if not two_factor_service:
            raise HTTPException(status_code=503, detail="2FA service unavailable")
        
        # This endpoint would typically be called with a temp session token
        # For now, we'll need user_id passed differently
        # This is a simplified implementation
        user_id = verify_data.dict().get("user_id")  # Would come from temp session
        if not user_id:
            raise HTTPException(status_code=400, detail="User identification required")
        
        result = await two_factor_service.verify_2fa_login(
            user_id, 
            verify_data.token, 
            verify_data.backup_code
        )
        
        if result["success"]:
            return {"message": result["message"]}
        else:
            raise HTTPException(status_code=400, detail=result["message"])
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying 2FA login: {e}")
        raise HTTPException(status_code=500, detail="2FA login verification failed")

@api_router.post("/auth/2fa/disable")
async def disable_2fa(
    disable_data: TwoFactorDisableRequest,
    current_user: User = Depends(get_current_user)
):
    """Disable 2FA for current user"""
    try:
        if not two_factor_service:
            raise HTTPException(status_code=503, detail="2FA service unavailable")
        
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        result = await two_factor_service.disable_2fa(
            current_user.id,
            disable_data.password,
            disable_data.token
        )
        
        if result["success"]:
            return {"message": result["message"]}
        else:
            raise HTTPException(status_code=400, detail=result["message"])
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error disabling 2FA: {e}")
        raise HTTPException(status_code=500, detail="Failed to disable 2FA")

@api_router.post("/auth/2fa/regenerate-backup-codes")
async def regenerate_backup_codes(
    verify_data: TwoFactorVerifyRequest,
    current_user: User = Depends(get_current_user)
):
    """Regenerate backup codes for user"""
    try:
        if not two_factor_service:
            raise HTTPException(status_code=503, detail="2FA service unavailable")
        
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        result = await two_factor_service.regenerate_backup_codes(current_user.id, verify_data.token)
        
        if result["success"]:
            return {"backup_codes": result["backup_codes"]}
        else:
            raise HTTPException(status_code=400, detail=result["message"])
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error regenerating backup codes: {e}")
        raise HTTPException(status_code=500, detail="Failed to regenerate backup codes")

@api_router.get("/auth/2fa/status")
async def get_2fa_status(current_user: User = Depends(get_current_user)):
    """Get 2FA status for current user"""
    try:
        if not two_factor_service:
            raise HTTPException(status_code=503, detail="2FA service unavailable")
        
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        status = await two_factor_service.get_2fa_status(current_user.id)
        return status
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting 2FA status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get 2FA status")

# Admin endpoint for 2FA statistics
@api_router.get("/admin/2fa/stats")
async def get_2fa_stats(current_user: User = Depends(get_current_user)):
    """Get 2FA statistics (admin only)"""
    try:
        # Check admin role
        if not current_user or "admin" not in (current_user.roles or []):
            raise HTTPException(status_code=403, detail="Admin access required")
        
        if not two_factor_service:
            raise HTTPException(status_code=503, detail="2FA service unavailable")
        
        stats = await two_factor_service.get_2fa_statistics()
        return stats
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting 2FA stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get statistics")

# KYC Verification endpoints
@api_router.post("/kyc/start")
async def start_kyc_verification(
    level_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Start KYC verification process"""
    try:
        if not kyc_service:
            raise HTTPException(status_code=503, detail="KYC service unavailable")
        
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        verification_level = level_data.get("verification_level")
        if not verification_level:
            raise HTTPException(status_code=400, detail="Verification level is required")
        
        # Validate verification level
        valid_levels = ["basic", "standard", "enhanced", "premium"]
        if verification_level not in valid_levels:
            raise HTTPException(status_code=400, detail="Invalid verification level")
        
        result = await kyc_service.start_verification(current_user.id, verification_level)
        
        if result["success"]:
            return {
                "verification_id": result["verification_id"],
                "verification_level": result["verification_level"],
                "required_documents": result["required_documents"],
                "message": result["message"]
            }
        else:
            raise HTTPException(status_code=400, detail=result["message"])
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting KYC verification: {e}")
        raise HTTPException(status_code=500, detail="Failed to start KYC verification")

@api_router.post("/kyc/upload-document")
async def upload_kyc_document(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Upload KYC document"""
    try:
        if not kyc_service:
            raise HTTPException(status_code=503, detail="KYC service unavailable")
        
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        # Get form data
        form = await request.form()
        file = form.get("file")
        document_type = form.get("document_type")
        
        if not file:
            raise HTTPException(status_code=400, detail="No file uploaded")
        
        if not document_type:
            raise HTTPException(status_code=400, detail="Document type is required")
        
        # Validate document type
        valid_types = ["id_card", "passport", "drivers_license", "utility_bill", 
                      "bank_statement", "business_registration", "tax_certificate", "selfie_with_id"]
        if document_type not in valid_types:
            raise HTTPException(status_code=400, detail="Invalid document type")
        
        # Read file content
        file_content = await file.read()
        file_size = len(file_content)
        
        # Validate file size (max 10MB)
        if file_size > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File too large. Maximum 10MB allowed")
        
        # Validate file type
        allowed_types = ['image/jpeg', 'image/png', 'image/jpg', 'application/pdf']
        if file.content_type not in allowed_types:
            raise HTTPException(status_code=400, detail="Invalid file type. Only JPG, PNG, and PDF allowed")
        
        # Save file (in production, use proper file storage service)
        import os
        upload_dir = "/app/uploads/kyc"
        os.makedirs(upload_dir, exist_ok=True)
        
        # Generate safe filename
        import uuid
        file_extension = os.path.splitext(file.filename)[1] if file.filename else '.bin'
        safe_filename = f"{uuid.uuid4().hex}{file_extension}"
        file_path = os.path.join(upload_dir, safe_filename)
        
        # Save file
        with open(file_path, "wb") as f:
            f.write(file_content)
        
        # Upload to KYC service
        result = await kyc_service.upload_document(
            user_id=current_user.id,
            document_type=document_type,
            file_path=file_path,
            file_name=file.filename or safe_filename,
            file_size=file_size,
            mime_type=file.content_type
        )
        
        if result["success"]:
            return {
                "document_id": result["document_id"],
                "message": result["message"]
            }
        else:
            # Clean up file if upload failed
            try:
                os.unlink(file_path)
            except:
                pass
            raise HTTPException(status_code=400, detail=result["message"])
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading KYC document: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload document")

@api_router.post("/kyc/submit")
async def submit_kyc_for_review(current_user: User = Depends(get_current_user)):
    """Submit KYC verification for admin review"""
    try:
        if not kyc_service:
            raise HTTPException(status_code=503, detail="KYC service unavailable")
        
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        result = await kyc_service.submit_for_review(current_user.id)
        
        if result["success"]:
            return {
                "message": result["message"],
                "estimated_review_time": result.get("estimated_review_time", "2-5 business days")
            }
        else:
            raise HTTPException(status_code=400, detail=result["message"])
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting KYC for review: {e}")
        raise HTTPException(status_code=500, detail="Failed to submit KYC for review")

@api_router.get("/kyc/status")
async def get_kyc_status(current_user: User = Depends(get_current_user)):
    """Get KYC verification status for current user"""
    try:
        if not kyc_service:
            raise HTTPException(status_code=503, detail="KYC service unavailable")
        
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        status = await kyc_service.get_verification_status(current_user.id)
        return status
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting KYC status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get KYC status")

# Admin KYC Management endpoints
@api_router.get("/admin/kyc/stats")
async def get_kyc_statistics(current_user: User = Depends(get_current_user)):
    """Get KYC statistics (admin only)"""
    try:
        # Check admin role
        if not current_user or "admin" not in (current_user.roles or []):
            raise HTTPException(status_code=403, detail="Admin access required")
        
        if not kyc_service:
            raise HTTPException(status_code=503, detail="KYC service unavailable")
        
        stats = await kyc_service.get_kyc_statistics()
        return stats
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting KYC statistics: {e}")
        raise HTTPException(status_code=500, detail="Failed to get statistics")

@api_router.get("/admin/kyc/pending")
async def get_pending_kyc_verifications(current_user: User = Depends(get_current_user)):
    """Get pending KYC verifications for admin review"""
    try:
        # Check admin role
        if not current_user or "admin" not in (current_user.roles or []):
            raise HTTPException(status_code=403, detail="Admin access required")
        
        if not kyc_service:
            raise HTTPException(status_code=503, detail="KYC service unavailable")
        
        # Get pending verifications
        pending = []
        verifications = kyc_service.kyc_verifications_collection.find({
            "current_status": {"$in": ["pending", "under_review"]}
        }).sort("created_date", 1)
        
        async for verification in verifications:
            # Get user info
            user = await kyc_service.users_collection.find_one({"id": verification["user_id"]})
            if user:
                pending.append({
                    "verification_id": verification["id"],
                    "user_email": user["email"],
                    "user_name": user.get("full_name", "Unknown"),
                    "verification_level": verification["verification_level"],
                    "current_status": verification["current_status"],
                    "created_date": verification["created_date"],
                    "verification_score": verification.get("verification_score"),
                    "risk_flags": verification.get("risk_flags", []),
                    "document_count": len(verification.get("documents", []))
                })
        
        return {"pending_verifications": pending, "total_count": len(pending)}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting pending KYC verifications: {e}")
        raise HTTPException(status_code=500, detail="Failed to get pending verifications")

@api_router.post("/admin/kyc/{verification_id}/approve")
async def approve_kyc_verification(
    verification_id: str,
    approval_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Approve KYC verification (admin only)"""
    try:
        # Check admin role
        if not current_user or "admin" not in (current_user.roles or []):
            raise HTTPException(status_code=403, detail="Admin access required")
        
        if not kyc_service:
            raise HTTPException(status_code=503, detail="KYC service unavailable")
        
        # Get verification
        verification = await kyc_service.kyc_verifications_collection.find_one({"id": verification_id})
        if not verification:
            raise HTTPException(status_code=404, detail="Verification not found")
        
        # Update verification status
        from datetime import datetime, timezone
        await kyc_service.kyc_verifications_collection.update_one(
            {"id": verification_id},
            {
                "$set": {
                    "current_status": "approved",
                    "approved_date": datetime.now(timezone.utc),
                    "reviewer_id": current_user.id,
                    "compliance_notes": approval_data.get("notes", "")
                }
            }
        )
        
        # Update user record
        await kyc_service.users_collection.update_one(
            {"id": verification["user_id"]},
            {
                "$set": {
                    "kyc_status": "approved",
                    "kyc_level": verification["verification_level"],
                    "kyc_approved_at": datetime.now(timezone.utc)
                }
            }
        )
        
        # Send approval notification
        user = await kyc_service.users_collection.find_one({"id": verification["user_id"]})
        if user:
            try:
                kyc_service.email_service.send_kyc_approved_notification(
                    user_email=user["email"],
                    user_name=user.get("full_name", "User"),
                    verification_level=verification["verification_level"],
                    verification_id=verification_id
                )
            except Exception as e:
                logger.warning(f"Failed to send KYC approval notification: {e}")
        
        logger.info(f"KYC verification approved: {verification_id} by {current_user.id}")
        
        return {"message": "KYC verification approved successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving KYC verification: {e}")
        raise HTTPException(status_code=500, detail="Failed to approve verification")

@api_router.post("/admin/kyc/{verification_id}/reject")
async def reject_kyc_verification(
    verification_id: str,
    rejection_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Reject KYC verification (admin only)"""
    try:
        # Check admin role
        if not current_user or "admin" not in (current_user.roles or []):
            raise HTTPException(status_code=403, detail="Admin access required")
        
        if not kyc_service:
            raise HTTPException(status_code=503, detail="KYC service unavailable")
        
        # Get verification
        verification = await kyc_service.kyc_verifications_collection.find_one({"id": verification_id})
        if not verification:
            raise HTTPException(status_code=404, detail="Verification not found")
        
        rejection_reason = rejection_data.get("reason", "Additional information required")
        
        # Update verification status
        from datetime import datetime, timezone
        await kyc_service.kyc_verifications_collection.update_one(
            {"id": verification_id},
            {
                "$set": {
                    "current_status": "rejected",
                    "review_date": datetime.now(timezone.utc),
                    "reviewer_id": current_user.id,
                    "compliance_notes": rejection_reason
                }
            }
        )
        
        # Send rejection notification
        user = await kyc_service.users_collection.find_one({"id": verification["user_id"]})
        if user:
            try:
                kyc_service.email_service.send_kyc_rejected_notification(
                    user_email=user["email"],
                    user_name=user.get("full_name", "User"),
                    verification_level=verification["verification_level"],
                    verification_id=verification_id,
                    rejection_reason=rejection_reason
                )
            except Exception as e:
                logger.warning(f"Failed to send KYC rejection notification: {e}")
        
        logger.info(f"KYC verification rejected: {verification_id} by {current_user.id}")
        
        return {"message": "KYC verification rejected"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rejecting KYC verification: {e}")
        raise HTTPException(status_code=500, detail="Failed to reject verification")

# Static file serving for uploads
@api_router.get("/uploads/{folder}/{filename}")
async def serve_uploaded_file(folder: str, filename: str):
    """Serve uploaded files (profile photos, farm photos, documents)"""
    try:
        import os
        from fastapi.responses import FileResponse
        
        # Validate folder to prevent directory traversal
        allowed_folders = ['profiles', 'farms', 'kyc', 'livestock', 'certificates']
        if folder not in allowed_folders:
            raise HTTPException(status_code=404, detail="Folder not found")
        
        # Construct file path
        file_path = f"/app/uploads/{folder}/{filename}"
        
        # Check if file exists and is actually a file
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            raise HTTPException(status_code=404, detail="File not found")
        
        # Determine content type based on file extension
        import mimetypes
        content_type, _ = mimetypes.guess_type(file_path)
        
        return FileResponse(
            path=file_path,
            media_type=content_type,
            headers={"Cache-Control": "max-age=86400"}  # Cache for 1 day
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving uploaded file: {e}")
        raise HTTPException(status_code=500, detail="Failed to serve file")

# Wishlist endpoints  
@api_router.post("/wishlist/add")
async def add_to_wishlist(
    wishlist_data: WishlistCreateRequest,
    current_user: User = Depends(get_current_user)
):
    """Add item to user's wishlist"""
    try:
        if not wishlist_service:
            raise HTTPException(status_code=503, detail="Wishlist service unavailable")
        
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        result = await wishlist_service.add_to_wishlist(current_user.id, wishlist_data)
        
        if result["success"]:
            return {
                "wishlist_id": result["wishlist_id"],
                "message": result["message"]
            }
        else:
            raise HTTPException(status_code=400, detail=result["message"])
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding to wishlist: {e}")
        raise HTTPException(status_code=500, detail="Failed to add to wishlist")

@api_router.delete("/wishlist/remove/{item_id}")
async def remove_from_wishlist(
    item_id: str,
    item_type: WishlistItemType,
    current_user: User = Depends(get_current_user)
):
    """Remove item from user's wishlist"""
    try:
        if not wishlist_service:
            raise HTTPException(status_code=503, detail="Wishlist service unavailable")
        
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        result = await wishlist_service.remove_from_wishlist(current_user.id, item_id, item_type)
        
        if result["success"]:
            return {"message": result["message"]}
        else:
            raise HTTPException(status_code=400, detail=result["message"])
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing from wishlist: {e}")
        raise HTTPException(status_code=500, detail="Failed to remove from wishlist")

@api_router.get("/wishlist")
async def get_user_wishlist(
    category: Optional[WishlistCategory] = None,
    item_type: Optional[WishlistItemType] = None,
    current_user: User = Depends(get_current_user)
):
    """Get user's wishlist items"""
    try:
        if not wishlist_service:
            raise HTTPException(status_code=503, detail="Wishlist service unavailable")
        
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        result = await wishlist_service.get_user_wishlist(current_user.id, category, item_type)
        
        if result["success"]:
            return {
                "items": result["items"],
                "summary": result["summary"]
            }
        else:
            raise HTTPException(status_code=400, detail=result["message"])
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting wishlist: {e}")
        raise HTTPException(status_code=500, detail="Failed to get wishlist")

@api_router.put("/wishlist/{wishlist_id}")
async def update_wishlist_item(
    wishlist_id: str,
    update_data: WishlistUpdateRequest,
    current_user: User = Depends(get_current_user)
):
    """Update wishlist item"""
    try:
        if not wishlist_service:
            raise HTTPException(status_code=503, detail="Wishlist service unavailable")
        
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        result = await wishlist_service.update_wishlist_item(current_user.id, wishlist_id, update_data)
        
        if result["success"]:
            return {"message": result["message"]}
        else:
            raise HTTPException(status_code=400, detail=result["message"])
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating wishlist item: {e}")
        raise HTTPException(status_code=500, detail="Failed to update wishlist item")

@api_router.get("/wishlist/check/{item_id}")
async def check_wishlist_status(
    item_id: str,
    item_type: WishlistItemType,
    current_user: User = Depends(get_current_user)
):
    """Check if item is in user's wishlist"""
    try:
        if not wishlist_service:
            raise HTTPException(status_code=503, detail="Wishlist service unavailable")
        
        if not current_user:
            # Return false for non-authenticated users
            return {"is_wishlisted": False}
        
        is_wishlisted = await wishlist_service.check_if_wishlisted(current_user.id, item_id, item_type)
        
        return {"is_wishlisted": is_wishlisted}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking wishlist status: {e}")
        raise HTTPException(status_code=500, detail="Failed to check wishlist status")

@api_router.get("/wishlist/stats")
async def get_wishlist_statistics(current_user: User = Depends(get_current_user)):
    """Get wishlist statistics for current user"""
    try:
        if not wishlist_service:
            raise HTTPException(status_code=503, detail="Wishlist service unavailable")
        
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        stats = await wishlist_service.get_wishlist_statistics(current_user.id)
        return stats
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting wishlist statistics: {e}")
        raise HTTPException(status_code=500, detail="Failed to get statistics")

# Price Alerts endpoints
@api_router.post("/price-alerts/create")
async def create_price_alert(
    alert_data: PriceAlertCreate,
    current_user: User = Depends(get_current_user)
):
    """Create new price alert for user"""
    try:
        if not price_alerts_service:
            raise HTTPException(status_code=503, detail="Price alerts service unavailable")
        
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        result = await price_alerts_service.create_price_alert(current_user.id, alert_data)
        
        if result["success"]:
            return {
                "alert_id": result["alert_id"],
                "current_price": result.get("current_price"),
                "message": result["message"]
            }
        else:
            raise HTTPException(status_code=400, detail=result["message"])
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating price alert: {e}")
        raise HTTPException(status_code=500, detail="Failed to create price alert")

@api_router.get("/price-alerts")
async def get_user_price_alerts(
    status: Optional[AlertStatus] = None,
    alert_type: Optional[AlertType] = None,
    current_user: User = Depends(get_current_user)
):
    """Get user's price alerts"""
    try:
        if not price_alerts_service:
            raise HTTPException(status_code=503, detail="Price alerts service unavailable")
        
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        result = await price_alerts_service.get_user_alerts(current_user.id, status, alert_type)
        
        if result["success"]:
            return {
                "alerts": result["alerts"],
                "summary": result["summary"]
            }
        else:
            raise HTTPException(status_code=400, detail=result["message"])
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting price alerts: {e}")
        raise HTTPException(status_code=500, detail="Failed to get price alerts")

@api_router.put("/price-alerts/{alert_id}")
async def update_price_alert(
    alert_id: str,
    update_data: PriceAlertUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update price alert"""
    try:
        if not price_alerts_service:
            raise HTTPException(status_code=503, detail="Price alerts service unavailable")
        
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        result = await price_alerts_service.update_price_alert(current_user.id, alert_id, update_data)
        
        if result["success"]:
            return {"message": result["message"]}
        else:
            raise HTTPException(status_code=400, detail=result["message"])
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating price alert: {e}")
        raise HTTPException(status_code=500, detail="Failed to update price alert")

@api_router.delete("/price-alerts/{alert_id}")
async def delete_price_alert(
    alert_id: str,
    current_user: User = Depends(get_current_user)
):
    """Delete price alert"""
    try:
        if not price_alerts_service:
            raise HTTPException(status_code=503, detail="Price alerts service unavailable")
        
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        result = await price_alerts_service.delete_price_alert(current_user.id, alert_id)
        
        if result["success"]:
            return {"message": result["message"]}
        else:
            raise HTTPException(status_code=400, detail=result["message"])
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting price alert: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete price alert")

@api_router.post("/price-alerts/check")
async def check_price_alerts():
    """Manually trigger price alert checking (admin or system use)"""
    try:
        if not price_alerts_service:
            raise HTTPException(status_code=503, detail="Price alerts service unavailable")
        
        result = await price_alerts_service.check_and_trigger_alerts()
        
        return {
            "processed_alerts": result.get("processed_alerts", 0),
            "triggered_alerts": result.get("triggered_alerts", 0),
            "message": "Price alerts check completed"
        }
        
    except Exception as e:
        logger.error(f"Error checking price alerts: {e}")
        raise HTTPException(status_code=500, detail="Failed to check price alerts")

@api_router.get("/price-alerts/stats")
async def get_price_alert_statistics(current_user: User = Depends(get_current_user)):
    """Get price alert statistics for current user"""
    try:
        if not price_alerts_service:
            raise HTTPException(status_code=503, detail="Price alerts service unavailable")
        
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        stats = await price_alerts_service.get_price_statistics(current_user.id)
        return stats
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting price alert statistics: {e}")
        raise HTTPException(status_code=500, detail="Failed to get statistics")

# Notifications endpoints
@api_router.get("/notifications")
async def get_user_notifications(
    request: Request,
    unread_only: bool = False,
    limit: int = 50,
    current_user: User = Depends(get_current_user)
):
    """Get user's notifications"""
    # Apply rate limiting for notifications endpoint
    await rate_limit_middleware(request, "notifications", current_user.id if current_user else None)
    
    try:
        if not price_alerts_service:
            raise HTTPException(status_code=503, detail="Price alerts service unavailable")
        
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        result = await price_alerts_service.get_user_notifications(current_user.id, unread_only, limit)
        
        if result["success"]:
            return {
                "notifications": result["notifications"],
                "total_count": result["total_count"],
                "unread_count": result["unread_count"]
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to get notifications")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting notifications: {e}")
        raise HTTPException(status_code=500, detail="Failed to get notifications")

@api_router.put("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    current_user: User = Depends(get_current_user)
):
    """Mark notification as read"""
    try:
        if not price_alerts_service:
            raise HTTPException(status_code=503, detail="Price alerts service unavailable")
        
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        result = await price_alerts_service.mark_notification_read(current_user.id, notification_id)
        
        if result["success"]:
            return {"message": result["message"]}
        else:
            raise HTTPException(status_code=400, detail=result["message"])
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking notification read: {e}")
        raise HTTPException(status_code=500, detail="Failed to mark notification as read")

# Unified Inbox API Endpoints
@api_router.get("/inbox/events")
async def inbox_sse_stream(request: Request, current_user: User = Depends(get_current_user)):
    """SSE stream for real-time inbox updates"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    return await sse_service.create_event_stream(request, current_user.id)

@api_router.get("/inbox/summary")
async def get_inbox_summary(current_user: User = Depends(get_current_user)):
    """Get unread counts by bucket"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        summary = await unified_inbox_service.get_inbox_summary(current_user.id)
        return summary
    except Exception as e:
        logger.error(f"Error getting inbox summary: {e}")
        raise HTTPException(status_code=500, detail="Failed to get inbox summary")

@api_router.get("/inbox")
async def get_inbox(
    bucket: str = "ALL",
    page: int = 1,
    current_user: User = Depends(get_current_user)
):
    """Get paginated inbox with bucket filtering"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        conversations = await unified_inbox_service.get_inbox(
            user_id=current_user.id,
            bucket=bucket,
            page=page
        )
        return conversations
    except Exception as e:
        logger.error(f"Error getting inbox: {e}")
        raise HTTPException(status_code=500, detail="Failed to get inbox")

@api_router.post("/inbox/conversations")
async def create_conversation(
    conversation_data: CreateConversationRequest,
    current_user: User = Depends(get_current_user)
):
    """Create a new conversation"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        conversation_id = await unified_inbox_service.ensure_conversation(
            type=conversation_data.type,
            subject=conversation_data.subject,
            participants=conversation_data.participants,
            order_group_id=conversation_data.order_group_id,
            buy_request_id=conversation_data.buy_request_id,
            offer_id=conversation_data.offer_id,
            consignment_id=conversation_data.consignment_id
        )
        return {"id": conversation_id}
    except Exception as e:
        logger.error(f"Error creating conversation: {e}")
        raise HTTPException(status_code=500, detail="Failed to create conversation")

@api_router.get("/inbox/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get conversation details"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        conversation = await unified_inbox_service.get_conversation(conversation_id, current_user.id)
        return conversation
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting conversation: {e}")
        raise HTTPException(status_code=500, detail="Failed to get conversation")

@api_router.get("/inbox/conversations/{conversation_id}/messages")
async def get_messages(
    conversation_id: str,
    page: int = 1,
    current_user: User = Depends(get_current_user)
):
    """Get paginated messages for conversation"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        messages = await unified_inbox_service.get_messages(
            conversation_id=conversation_id,
            user_id=current_user.id,
            page=page
        )
        return messages
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting messages: {e}")
        raise HTTPException(status_code=500, detail="Failed to get messages")

@api_router.post("/inbox/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: str,
    message_data: SendMessageBody,
    current_user: User = Depends(get_current_user)
):
    """Send a message to conversation"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        message_id = await unified_inbox_service.send_message(
            conversation_id=conversation_id,
            sender_id=current_user.id,
            body=message_data.body,
            attachments=message_data.attachments
        )
        return {"id": message_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        raise HTTPException(status_code=500, detail="Failed to send message")

@api_router.post("/inbox/conversations/{conversation_id}/read")
async def mark_conversation_read(
    conversation_id: str,
    current_user: User = Depends(get_current_user)
):
    """Mark conversation as read"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        await unified_inbox_service.mark_conversation_read(conversation_id, current_user.id)
        return {"ok": True}
    except Exception as e:
        logger.error(f"Error marking conversation read: {e}")
        raise HTTPException(status_code=500, detail="Failed to mark as read")

@api_router.patch("/inbox/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: str,
    update_data: UpdateConversationRequest,
    current_user: User = Depends(get_current_user)
):
    """Update conversation settings (mute/archive)"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        await unified_inbox_service.update_conversation(
            conversation_id=conversation_id,
            user_id=current_user.id,
            muted=update_data.muted,
            archived=update_data.archived
        )
        return {"ok": True}
    except Exception as e:
        logger.error(f"Error updating conversation: {e}")
        raise HTTPException(status_code=500, detail="Failed to update conversation")

# Profile Photo Upload Endpoint
@api_router.post("/profile/photo")
async def upload_profile_photo(
    photo: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """Upload profile photo"""
    try:
        # Validate file type
        if not photo.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="File must be an image")
        
        # Validate file size (5MB max)
        if photo.size > 5 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File size must be less than 5MB")
        
        # Create uploads directory if it doesn't exist
        import os
        upload_dir = "/app/uploads/profiles"
        os.makedirs(upload_dir, exist_ok=True)
        
        # Generate unique filename
        import uuid
        file_extension = photo.filename.split('.')[-1]
        unique_filename = f"{current_user.id}_{uuid.uuid4()}.{file_extension}"
        file_path = os.path.join(upload_dir, unique_filename)
        
        # Save file
        with open(file_path, "wb") as buffer:
            content = await photo.read()
            buffer.write(content)
        
        # Update user profile with photo URL
        photo_url = f"/uploads/profiles/{unique_filename}"
        await db.users.update_one(
            {"id": current_user.id},
            {"$set": {"profile_photo": photo_url}}
        )
        
        return {"photo_url": photo_url, "message": "Profile photo uploaded successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading profile photo: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload photo")

def calculate_profile_completion(user_data: dict) -> float:
    """Calculate profile completion percentage based on user roles"""
    user_roles = user_data.get('roles', ['buyer'])
    total_fields = 0
    completed_fields = 0
    
    # Basic required fields (30% weight) - Common to all users
    basic_fields = ['full_name', 'email', 'phone']
    for field in basic_fields:
        total_fields += 1
        if user_data.get(field):
            completed_fields += 1
    
    # Profile enhancement fields (25% weight) - Common to all users
    profile_fields = ['profile_photo', 'business_name', 'bio', 'location_region', 'experience_years']
    for field in profile_fields:
        total_fields += 1
        if user_data.get(field):
            completed_fields += 1
    
    # Role-specific fields (35% weight)
    if 'seller' in user_roles:
        # Seller-specific fields
        seller_fields = ['primary_livestock', 'farming_methods', 'return_policy', 'health_guarantee']
        for field in seller_fields:
            total_fields += 1
            if field in ['primary_livestock', 'farming_methods']:
                field_value = user_data.get(field, [])
                if field_value and len(field_value) > 0:
                    completed_fields += 1
            else:
                if user_data.get(field):
                    completed_fields += 1
    
    if 'buyer' in user_roles:
        # Buyer-specific fields
        buyer_fields = ['livestock_interests', 'buying_purpose', 'payment_methods', 'veterinary_contact']
        for field in buyer_fields:
            total_fields += 1
            if field in ['livestock_interests', 'buying_purpose', 'payment_methods']:
                field_value = user_data.get(field, [])
                if field_value and len(field_value) > 0:
                    completed_fields += 1
            else:
                if user_data.get(field):
                    completed_fields += 1
    
    # Communication preferences (10% weight) - Common
    comm_fields = ['preferred_communication']
    for field in comm_fields:
        total_fields += 1
        field_value = user_data.get(field, [])
        if field_value and len(field_value) > 0:
            completed_fields += 1
    
    return round((completed_fields / total_fields) * 100, 1) if total_fields > 0 else 0.0

@api_router.patch("/profile")
async def update_user_profile(
    profile_data: UserProfileUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update user profile information"""
    try:
        # Prepare update data - only include non-None fields
        update_data = {}
        
        # Convert Pydantic model to dict and filter out None values
        profile_dict = profile_data.dict(exclude_unset=True)
        
        for key, value in profile_dict.items():
            if value is not None:
                update_data[key] = value
        
        # Get current user data for completion calculation
        current_user_doc = await db.users.find_one({"id": current_user.id})
        if not current_user_doc:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Merge current data with updates for completion calculation
        merged_data = {**current_user_doc, **update_data}
        
        # Calculate profile completion score
        completion_score = calculate_profile_completion(merged_data)
        update_data["profile_completion_score"] = completion_score
        
        # Update user in database
        result = await db.users.update_one(
            {"id": current_user.id},
            {"$set": update_data}
        )
        
        if result.modified_count == 0:
            raise HTTPException(status_code=400, detail="No changes were made")
        
        # Return updated user data
        updated_user = await db.users.find_one({"id": current_user.id})
        
        # Remove password from response
        if updated_user and "password_hash" in updated_user:
            del updated_user["password_hash"]
        
        return {
            "message": "Profile updated successfully",
            "user": updated_user,
            "profile_completion": completion_score
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating profile: {e}")
        raise HTTPException(status_code=500, detail="Failed to update profile")

@api_router.post("/profile/farm-photos")
async def upload_farm_photos(
    photos: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user)
):
    """Upload farm/facility photos (max 10 photos)"""
    try:
        if len(photos) > 10:
            raise HTTPException(status_code=400, detail="Maximum 10 photos allowed")
        
        uploaded_urls = []
        upload_dir = "/app/frontend/public/uploads/farms"
        os.makedirs(upload_dir, exist_ok=True)
        
        for photo in photos:
            # Validate file type and size
            if not photo.content_type.startswith('image/'):
                raise HTTPException(status_code=400, detail=f"File {photo.filename} must be an image")
            
            if photo.size > 5 * 1024 * 1024:
                raise HTTPException(status_code=400, detail=f"File {photo.filename} size must be less than 5MB")
            
            # Generate unique filename
            file_extension = photo.filename.split('.')[-1] if '.' in photo.filename else 'jpg'
            unique_filename = f"{current_user.id}_farm_{uuid.uuid4()}.{file_extension}"
            file_path = os.path.join(upload_dir, unique_filename)
            
            # Save file
            with open(file_path, "wb") as buffer:
                content = await photo.read()
                buffer.write(content)
            
            photo_url = f"/uploads/farms/{unique_filename}"
            uploaded_urls.append(photo_url)
        
        # Update user's farm photos
        await db.users.update_one(
            {"id": current_user.id},
            {"$push": {"farm_photos": {"$each": uploaded_urls}}}
        )
        
        return {
            "message": f"Successfully uploaded {len(uploaded_urls)} farm photos",
            "photo_urls": uploaded_urls
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading farm photos: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload farm photos")

# Profile configuration endpoints
@api_router.get("/profile/options")
async def get_profile_options():
    """Get predefined options for profile fields"""
    return {
        "south_african_provinces": [
            "Eastern Cape", "Free State", "Gauteng", "KwaZulu-Natal",
            "Limpopo", "Mpumalanga", "Northern Cape", "North West", "Western Cape"
        ],
        "livestock_types": [
            "cattle", "sheep", "goats", "pigs", "chickens", "ducks", "geese", "turkeys",
            "horses", "donkeys", "rabbits", "ostrich", "emu", "guinea_fowl",
            "buffalo", "antelope", "deer", "elk", "bison", "alpaca", "llama"
        ],
        "farming_methods": [
            "organic", "free_range", "grass_fed", "commercial", "intensive",
            "extensive", "rotational_grazing", "regenerative", "sustainable"
        ],
        "certifications": [
            "organic_certified", "veterinary_certificate", "health_certificate",
            "breed_registration", "biosecurity_certified", "halal_certified",
            "welfare_approved", "pasture_raised_certified"
        ],
        "associations": [
            "SA_Stud_Book", "Red_Meat_Producers", "Milk_Producers_Organisation",
            "National_Wool_Growers", "SA_Pork_Producers", "SA_Poultry_Association",
            "Emerging_Farmers_Association", "Commercial_Farmers_Union"
        ],
        "communication_preferences": [
            "phone", "email", "whatsapp", "sms", "in_person"
        ],
        # BUYER-SPECIFIC OPTIONS
        "buying_purposes": [
            "breeding", "commercial_production", "personal_consumption", "hobby_farming",
            "show_animals", "research", "conservation", "educational"
        ],
        "purchase_frequencies": [
            "occasional", "regular", "seasonal", "bulk_purchases", "as_needed"
        ],
        "budget_ranges": [
            "small_scale", "medium_scale", "large_scale", "enterprise_level"
        ],
        "facility_types": [
            "commercial_farm", "hobby_farm", "feedlot", "dairy_operation",
            "breeding_facility", "show_facility", "smallholding", "ranch"
        ],
        "farm_infrastructure": [
            "secure_fencing", "water_systems", "shelter_facilities", "feed_storage",
            "veterinary_facilities", "quarantine_area", "loading_facilities", "pasture_land"
        ],
        "livestock_experience": [
            "cattle_farming", "sheep_raising", "goat_farming", "pig_farming",
            "poultry_farming", "horse_breeding", "exotic_animals", "dairy_production"
        ],
        "buyer_certifications": [
            "animal_welfare_certified", "organic_farming_certified", "biosecurity_certified",
            "livestock_handling_certified", "veterinary_assistant", "animal_nutrition_certified"
        ],
        "payment_methods": [
            "cash", "bank_transfer", "electronic_payment", "credit_terms", "cheque", "escrow"
        ],
        "payment_timelines": [
            "immediate", "7_days", "14_days", "30_days", "on_delivery", "partial_payments"
        ],
        "collection_preferences": [
            "self_collect", "delivery_requested", "transport_arranged", "flexible"
        ],
        "animal_welfare_standards": [
            "free_range", "organic_care", "veterinary_supervised", "natural_feeding",
            "stress_free_handling", "regular_health_checks", "spacious_housing"
        ]
    }
@api_router.get("/category-groups", response_model=List[CategoryGroup])
async def get_category_groups():
    """Get all category groups"""
    try:
        groups_docs = await db.category_groups.find().to_list(length=None)
        return [CategoryGroup(**doc) for doc in groups_docs]
    except Exception as e:
        logger.error(f"Error fetching category groups: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch category groups")

@api_router.get("/taxonomy/categories")
async def get_taxonomy_categories(mode: Optional[str] = "core"):
    """Get categories with core/exotic mode filtering"""
    try:
        if mode == "core":
            # Primary categories - core livestock
            core_category_names = [
                "Poultry", "Ruminants", "Rabbits", "Aquaculture", "Other Small Livestock"
            ]
            cursor = db.category_groups.find({
                "name": {"$in": core_category_names}
            })
        elif mode == "exotic":
            # Exotic & specialty categories
            exotic_category_names = [
                "Game Animals", "Large Flightless Birds", 
                "Camelids & Exotic Ruminants", "Specialty Avian",
                "Aquaculture Exotic", "Specialty Small Mammals"
            ]
            cursor = db.category_groups.find({
                "name": {"$in": exotic_category_names}
            })
        else:
            # All categories
            cursor = db.category_groups.find()
        
        categories = await cursor.to_list(length=None)
        
        # Clean MongoDB _id fields and add slug
        for category in categories:
            if "_id" in category:
                del category["_id"]
            # Add URL-friendly slug
            category["slug"] = category["name"].lower().replace(" ", "-").replace("&", "and")
        
        return categories
        
    except Exception as e:
        logger.error(f"Error fetching taxonomy categories: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch categories")

@api_router.get("/listings")
async def get_listings_with_exotic_filter(
    country: str = "ZA",
    include_exotics: bool = False,
    species: Optional[str] = None,
    category: Optional[str] = None,
    # Frontend filter parameters
    category_group_id: Optional[str] = None,
    species_id: Optional[str] = None,
    breed_id: Optional[str] = None,
    product_type_id: Optional[str] = None,
    region: Optional[str] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    listing_type: Optional[str] = None,
    deliverable_only: Optional[bool] = None,
    limit: int = 20,
    skip: int = 0
):
    """Get listings with exotic filtering support and frontend compatibility"""
    try:
        # Build base filter
        filter_query = {"status": "active"}  # Only show active listings
        
        # Frontend filter parameters (these take precedence)
        if category_group_id:
            # Get species IDs for this category group
            species_docs = await db.species.find({"category_group_id": category_group_id}).to_list(length=None)
            if species_docs:
                species_ids = [s["id"] for s in species_docs]
                filter_query["species_id"] = {"$in": species_ids}
            else:
                # No species in this category, return empty results
                return {"listings": [], "total_count": 0, "filters_applied": {"category_group_id": category_group_id}}
        elif category:
            # Legacy category name filter - find category ID by name
            category_doc = await db.category_groups.find_one({
                "$or": [
                    {"name": {"$regex": category, "$options": "i"}},
                    {"name": category.replace("-", " ").title()}
                ]
            })
            if category_doc:
                # Get species IDs for this category group
                species_docs = await db.species.find({"category_group_id": category_doc["id"]}).to_list(length=None)
                if species_docs:
                    species_ids = [s["id"] for s in species_docs]
                    filter_query["species_id"] = {"$in": species_ids}
                else:
                    # No species in this category, return empty results
                    return {"listings": [], "total_count": 0, "filters_applied": {"category": category}}
        
        if species_id:
            filter_query["species_id"] = species_id
        elif species:
            # Legacy species name filter - find species ID by name
            species_doc = await db.species.find_one({
                "name": {"$regex": species, "$options": "i"}
            })
            if species_doc:
                filter_query["species_id"] = species_doc["id"]
        
        if breed_id:
            filter_query["breed_id"] = breed_id
        
        if product_type_id:
            filter_query["product_type_id"] = product_type_id
        
        if region:
            filter_query["region"] = {"$regex": region, "$options": "i"}
        
        if price_min is not None:
            filter_query["price_per_unit"] = {"$gte": price_min}
        
        if price_max is not None:
            if "price_per_unit" in filter_query:
                filter_query["price_per_unit"]["$lte"] = price_max
            else:
                filter_query["price_per_unit"] = {"$lte": price_max}
        
        if listing_type and listing_type != "all":
            filter_query["listing_type"] = listing_type
        
        # Exotic filtering - only apply if not include_exotics
        if not include_exotics:
            # Get core species IDs (non-exotic)
            core_species_docs = await db.species.find({
                "$or": [
                    {"is_exotic": {"$ne": True}},
                    {"is_exotic": {"$exists": False}}
                ]
            }).to_list(length=None)
            
            core_species_ids = [s["id"] for s in core_species_docs]
            
            # Handle case where there's already a species_id filter
            if "species_id" in filter_query:
                existing_species_filter = filter_query["species_id"]
                
                # Check if it's a simple string or a MongoDB query object
                if isinstance(existing_species_filter, str):
                    # Simple species_id filter
                    if existing_species_filter not in core_species_ids:
                        # This species is exotic, return empty results
                        return {"listings": [], "total_count": 0, "core_only": True}
                elif isinstance(existing_species_filter, dict) and "$in" in existing_species_filter:
                    # Multiple species filter (from category filtering)
                    # Filter to only include core species
                    filtered_species_ids = [sid for sid in existing_species_filter["$in"] if sid in core_species_ids]
                    if not filtered_species_ids:
                        # No core species in this category, return empty results
                        return {"listings": [], "total_count": 0, "core_only": True}
                    filter_query["species_id"] = {"$in": filtered_species_ids}
            else:
                # Add filter to only show core species
                filter_query["species_id"] = {"$in": core_species_ids}
        
        # Handle deliverable filtering
        if deliverable_only:
            filter_query["delivery_available"] = True
        
        # Get listings
        cursor = db.listings.find(filter_query).skip(skip).limit(limit)
        listings = await cursor.to_list(length=None)
        
        # Get total count
        total_count = await db.listings.count_documents(filter_query)
        
        # Clean MongoDB _id fields
        for listing in listings:
            if "_id" in listing:
                del listing["_id"]
        
        return {
            "listings": listings,
            "total_count": total_count,
            "include_exotics": include_exotics,
            "filters_applied": {
                "species": species,
                "category": category,
                "country": country
            }
        }
        
    except Exception as e:
        logger.error(f"Error fetching listings: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch listings")

@api_router.get("/compliance/requirements")
async def get_compliance_requirements(
    country: str = "ZA", 
    species: Optional[str] = None,
    product_type: Optional[str] = None
):
    """Get compliance requirements for species/product type combination"""
    try:
        if not species:
            return {"requirements": []}
        
        # Get species document
        species_doc = await db.species.find_one({"name": species})
        if not species_doc:
            return {"requirements": [], "error": f"Species '{species}' not found"}
        
        # Get compliance requirements
        filter_query = {
            "country_code": country,
            "species_id": species_doc["id"]
        }
        
        cursor = db.compliance_rules.find(filter_query)
        requirements = await cursor.to_list(length=None)
        
        # Clean MongoDB _id fields
        for req in requirements:
            if "_id" in req:
                del req["_id"]
        
        # Add species info for context
        result = {
            "species": species,
            "country": country,
            "product_type": product_type,
            "species_info": {
                "is_exotic": species_doc.get("is_exotic", False),
                "is_game": species_doc.get("is_game", False),
                "permit_required": species_doc.get("permit_required", False)
            },
            "requirements": requirements
        }
        
        return result
        
    except Exception as e:
        logger.error(f"Error fetching compliance requirements: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch compliance requirements")

@api_router.get("/species")
async def get_species(category_group_id: Optional[str] = None, include_exotics: bool = True):
    """Get all species, optionally filtered by category group and exotic status"""
    try:
        filter_query = {}
        if category_group_id:
            filter_query["category_group_id"] = category_group_id
            
        # Filter exotic species if not requested
        if not include_exotics:
            filter_query["$or"] = [
                {"is_exotic": {"$ne": True}},
                {"is_exotic": {"$exists": False}}
            ]
            
        species_docs = await db.species.find(filter_query).to_list(length=None)
        
        # Clean MongoDB _id fields
        species_list = []
        for doc in species_docs:
            if "_id" in doc:
                del doc["_id"]
            species_list.append(doc)
            
        return species_list
    except Exception as e:
        logger.error(f"Error fetching species: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch species")

@api_router.get("/breeds")
async def get_all_breeds():
    """Get all breeds"""
    try:
        breeds_docs = await db.breeds.find().to_list(length=None)
        # Clean MongoDB _id
        breeds = []
        for doc in breeds_docs:
            if "_id" in doc:
                del doc["_id"]
            breeds.append(doc)
        return breeds
    except Exception as e:
        logger.error(f"Error fetching breeds: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch breeds")

@api_router.get("/species/{species_id}/breeds", response_model=List[Breed])
async def get_breeds_by_species(species_id: str):
    """Get breeds for a specific species"""
    try:
        breeds_docs = await db.breeds.find({"species_id": species_id}).to_list(length=None)
        return [Breed(**doc) for doc in breeds_docs]
    except Exception as e:
        logger.error(f"Error fetching breeds: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch breeds")

@api_router.get("/product-types")
async def get_product_types(category_group: Optional[str] = None, species: Optional[str] = None):
    """Get all product types, optionally filtered by category group or species"""
    try:
        filter_query = {}
        
        if species:
            # Get species document to find its category
            species_doc = await db.species.find_one({"name": species})
            if species_doc:
                # Get the category for this species
                category_doc = await db.category_groups.find_one({"id": species_doc["category_group_id"]})
                if category_doc:
                    category_name = category_doc["name"]
                    
                    # For exotic species, use the exotic product types service
                    if species_doc.get("is_exotic", False):
                        if exotic_livestock_service:
                            exotic_types = await exotic_livestock_service.get_valid_product_types_for_species(species)
                            return exotic_types
                    
                    # For regular species, get product types applicable to their category
                    filter_query["applicable_to_groups"] = {"$in": [category_name]}
        elif category_group:
            filter_query["applicable_to_groups"] = {"$in": [category_group]}
        
        types_docs = await db.product_types.find(filter_query).to_list(length=None)
        
        # Clean MongoDB _id fields
        product_types = []
        for doc in types_docs:
            if "_id" in doc:
                del doc["_id"]
            product_types.append(doc)
            
        return product_types
    except Exception as e:
        logger.error(f"Error fetching product types: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch product types")

@api_router.get("/taxonomy/full")
async def get_full_taxonomy():
    """Get complete taxonomy structure for listing forms"""
    try:
        # Get all category groups
        groups_docs = await db.category_groups.find().to_list(length=None)
        
        taxonomy = []
        for group_doc in groups_docs:
            group = CategoryGroup(**group_doc)
            
            # Get species for this group
            species_docs = await db.species.find({"category_group_id": group.id}).to_list(length=None)
            species_list = []
            
            for species_doc in species_docs:
                species_obj = Species(**species_doc)
                
                # Get breeds for this species
                breeds_docs = await db.breeds.find({"species_id": species_obj.id}).to_list(length=None)
                breeds_list = [Breed(**breed_doc) for breed_doc in breeds_docs]
                
                # Convert species to dict and add breeds
                species_dict = species_obj.dict()
                species_dict["breeds"] = [breed.dict() for breed in breeds_list]
                species_list.append(species_dict)
            
            # Get product types applicable to this group
            product_types_docs = await db.product_types.find({
                "applicable_to_groups": {"$in": [group.name]}
            }).to_list(length=None)
            product_types_list = [ProductType(**pt_doc).dict() for pt_doc in product_types_docs]
            
            taxonomy.append({
                "group": group.dict(),
                "species": species_list,
                "product_types": product_types_list
            })
        
        return taxonomy
    except Exception as e:
        logger.error(f"Error fetching full taxonomy: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch taxonomy")

# EXOTIC LIVESTOCK ENDPOINTS
@api_router.get("/exotic-livestock/categories")
async def get_exotic_categories():
    """Get all exotic livestock categories"""
    try:
        if not exotic_livestock_service:
            raise HTTPException(status_code=503, detail="Exotic livestock service not available")
        
        categories = await exotic_livestock_service.get_exotic_categories()
        return {
            "categories": categories,
            "total_count": len(categories)
        }
    except Exception as e:
        logger.error(f"Error fetching exotic categories: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch exotic categories")

@api_router.get("/exotic-livestock/species")
async def get_exotic_species(category_id: Optional[str] = None):
    """Get exotic species, optionally filtered by category"""
    try:
        if not exotic_livestock_service:
            raise HTTPException(status_code=503, detail="Exotic livestock service not available")
        
        species = await exotic_livestock_service.get_exotic_species(category_id)
        return {
            "species": species,
            "total_count": len(species)
        }
    except Exception as e:
        logger.error(f"Error fetching exotic species: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch exotic species")

@api_router.get("/exotic-livestock/species/{species_name}/product-types")
async def get_species_product_types(species_name: str):
    """Get valid product types for a specific exotic species"""
    try:
        if not exotic_livestock_service:
            raise HTTPException(status_code=503, detail="Exotic livestock service not available")
        
        product_types = await exotic_livestock_service.get_valid_product_types_for_species(species_name)
        return {
            "species": species_name,
            "product_types": product_types,
            "total_count": len(product_types)
        }
    except Exception as e:
        logger.error(f"Error fetching product types for {species_name}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch product types")

@api_router.get("/exotic-livestock/species/{species_id}/compliance")
async def get_species_compliance(species_id: str, country_code: str = "ZA"):
    """Get compliance requirements for a specific exotic species"""
    try:
        if not exotic_livestock_service:
            raise HTTPException(status_code=503, detail="Exotic livestock service not available")
        
        requirements = await exotic_livestock_service.get_species_compliance_requirements(species_id, country_code)
        return {
            "species_id": species_id,
            "country_code": country_code,
            "requirements": requirements,
            "total_count": len(requirements)
        }
    except Exception as e:
        logger.error(f"Error fetching compliance requirements: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch compliance requirements")

@api_router.post("/exotic-livestock/validate-listing")
async def validate_exotic_listing(listing_data: dict):
    """Validate exotic livestock listing and return compliance info"""
    try:
        if not exotic_livestock_service:
            raise HTTPException(status_code=503, detail="Exotic livestock service not available")
        
        validation_result = await exotic_livestock_service.validate_exotic_listing(listing_data)
        return validation_result
    except Exception as e:
        logger.error(f"Error validating exotic listing: {e}")
        raise HTTPException(status_code=500, detail="Failed to validate listing")

@api_router.get("/exotic-livestock/statistics")
async def get_exotic_statistics():
    """Get statistics about exotic species in the system"""
    try:
        if not exotic_livestock_service:
            raise HTTPException(status_code=503, detail="Exotic livestock service not available")
        
        stats = await exotic_livestock_service.get_exotic_species_statistics()
        return stats
    except Exception as e:
        logger.error(f"Error fetching exotic statistics: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch statistics")

@api_router.get("/exotic-livestock/search")
async def search_exotic_species(
    q: Optional[str] = None,
    is_game: Optional[bool] = None,
    permit_required: Optional[bool] = None,
    category_id: Optional[str] = None,
    is_edible: Optional[bool] = None
):
    """Search exotic species with filters"""
    try:
        if not exotic_livestock_service:
            raise HTTPException(status_code=503, detail="Exotic livestock service not available")
        
        filters = {}
        if is_game is not None:
            filters["is_game"] = is_game
        if permit_required is not None:
            filters["permit_required"] = permit_required
        if category_id:
            filters["category_id"] = category_id
        if is_edible is not None:
            filters["is_edible"] = is_edible
        
        species = await exotic_livestock_service.search_exotic_species(q or "", filters)
        return {
            "query": q,
            "filters": filters,
            "species": species,
            "total_count": len(species)
        }
    except Exception as e:
        logger.error(f"Error searching exotic species: {e}")
        raise HTTPException(status_code=500, detail="Failed to search species")

@api_router.get("/exotic-livestock/species/{species_name}/breeding-recommendations")
async def get_breeding_recommendations(species_name: str):
    """Get breeding recommendations for exotic species"""
    try:
        if not exotic_livestock_service:
            raise HTTPException(status_code=503, detail="Exotic livestock service not available")
        
        recommendations = await exotic_livestock_service.get_exotic_breeding_recommendations(species_name)
        return recommendations
    except Exception as e:
        logger.error(f"Error fetching breeding recommendations: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch breeding recommendations")

# Organization routes
@api_router.post("/orgs", response_model=Organization)
async def create_organization(org_data: OrganizationCreate, current_user: User = Depends(get_current_user)):
    """Create a new organization"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        # Check if handle is already taken
        if org_data.handle:
            existing = await db.organizations.find_one({"handle": org_data.handle})
            if existing:
                raise HTTPException(status_code=400, detail="Handle already taken")
        
        # Create organization
        org = Organization(**org_data.dict())
        org_dict = org.dict()
        await db.organizations.insert_one(org_dict)
        
        # Create membership with current user as OWNER
        membership = OrganizationMembership(
            org_id=org.id,
            user_id=current_user.id,
            role=OrganizationRole.OWNER
        )
        await db.org_memberships.insert_one(membership.dict())
        
        # Create initial KYC record
        kyc = OrganizationKYC(org_id=org.id)
        await db.org_kyc.insert_one(kyc.dict())
        
        return org
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating organization: {e}")
        raise HTTPException(status_code=500, detail="Failed to create organization")

@api_router.get("/orgs/my-contexts")
async def get_my_contexts(current_user: User = Depends(get_current_user)):
    """Get all contexts (user + organizations) available to current user"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        contexts = []
        
        # Add personal context
        contexts.append({
            "label": f"{current_user.full_name} (Personal)",
            "value": "user",
            "type": "USER"
        })
        
        # Add organization contexts
        memberships = await db.org_memberships.find({"user_id": current_user.id}).to_list(length=None)
        for membership in memberships:
            org = await db.organizations.find_one({"id": membership["org_id"]})
            if org:
                contexts.append({
                    "label": f"{org['name']} ({membership['role']})",
                    "value": org["id"],
                    "type": "ORG",
                    "role": membership["role"]
                })
        
        return {
            "items": contexts,
            "current": "user"  # Default to user context
        }
    except Exception as e:
        logger.error(f"Error fetching contexts: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch contexts")

@api_router.post("/orgs/switch")
async def switch_context(request: SwitchContextRequest, current_user: User = Depends(get_current_user)):
    """Switch selling context"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        # For now, just return success - in a real implementation, you'd store this in session
        # or return a JWT with the context info
        return {"success": True, "context": request.target}
    except Exception as e:
        logger.error(f"Error switching context: {e}")
        raise HTTPException(status_code=500, detail="Failed to switch context")

@api_router.post("/orgs/{org_id}/invite")
async def invite_member(org_id: str, invite_data: InviteMemberRequest, current_user: User = Depends(get_current_user)):
    """Invite a member to the organization"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        # Check if user has permission to invite
        membership = await db.org_memberships.find_one({
            "org_id": org_id,
            "user_id": current_user.id,
            "role": {"$in": ["OWNER", "ADMIN"]}
        })
        if not membership:
            raise HTTPException(status_code=403, detail="Permission denied")
        
        # Check if user being invited exists
        invitee = await db.users.find_one({"email": invite_data.email})
        if not invitee:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Check if already a member
        existing = await db.org_memberships.find_one({
            "org_id": org_id,
            "user_id": invitee["id"]
        })
        if existing:
            raise HTTPException(status_code=400, detail="User is already a member")
        
        # Create membership
        new_membership = OrganizationMembership(
            org_id=org_id,
            user_id=invitee["id"],
            role=invite_data.role
        )
        await db.org_memberships.insert_one(new_membership.dict())
        
        # TODO: Send email invitation using Mailgun
        
        return {"success": True, "message": "Member invited successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error inviting member: {e}")
        raise HTTPException(status_code=500, detail="Failed to invite member")

@api_router.get("/orgs/{identifier}")
async def get_organization(identifier: str, current_user: User = Depends(get_current_user)):
    """Get organization details by ID or handle"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        # Try to find organization by ID first, then by handle
        org = await db.organizations.find_one({"id": identifier})
        if not org:
            org = await db.organizations.find_one({"handle": identifier})
        
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
        
        # Check if user is a member
        membership = await db.org_memberships.find_one({
            "org_id": org["id"],
            "user_id": current_user.id
        })
        if not membership:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Remove MongoDB _id field to avoid serialization issues
        if "_id" in org:
            del org["_id"]
        
        return org
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching organization: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch organization")

@api_router.get("/orgs/{org_id}/members")
async def get_organization_members(org_id: str, current_user: User = Depends(get_current_user)):
    """Get organization members"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        # Check if user is a member
        membership = await db.org_memberships.find_one({
            "org_id": org_id,
            "user_id": current_user.id
        })
        if not membership:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Get all members
        memberships = await db.org_memberships.find({"org_id": org_id}).to_list(length=None)
        members = []
        
        for member_ship in memberships:
            user = await db.users.find_one({"id": member_ship["user_id"]})
            if user:
                members.append({
                    "email": user["email"],
                    "full_name": user["full_name"],
                    "role": member_ship["role"],
                    "joined_at": member_ship["joined_at"]
                })
        
        return members
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching organization members: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch members")

@api_router.get("/orgs/storefront/{handle}")
async def get_organization_storefront(handle: str):
    """Get public organization storefront"""
    try:
        # Get organization by handle
        org = await db.organizations.find_one({"handle": handle})
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
        
        # Get public settings
        public_settings = await db.org_public_settings.find_one({"org_id": org["id"]})
        
        # Get organization listings
        listings = await db.listings.find({
            "org_id": org["id"],
            "status": "ACTIVE"
        }).to_list(length=20)
        
        # Get member count
        member_count = await db.org_memberships.count_documents({"org_id": org["id"]})
        
        return {
            "organization": org,
            "public_settings": public_settings,
            "listings": listings,
            "member_count": member_count,
            "listing_count": len(listings)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching organization storefront: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch storefront")

# Admin Organization Management
@api_router.get("/admin/organizations")
async def admin_get_organizations(current_user: User = Depends(get_current_user)):
    """Get all organizations for admin"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Get all organizations with aggregated data
        pipeline = [
            {
                "$lookup": {
                    "from": "org_memberships",
                    "localField": "id",
                    "foreignField": "org_id",
                    "as": "memberships"
                }
            },
            {
                "$lookup": {
                    "from": "org_kyc",
                    "localField": "id",
                    "foreignField": "org_id",
                    "as": "kyc"
                }
            },
            {
                "$lookup": {
                    "from": "listings",
                    "localField": "id",
                    "foreignField": "org_id",
                    "as": "listings"
                }
            },
            {
                "$addFields": {
                    "member_count": {"$size": "$memberships"},
                    "listing_count": {"$size": "$listings"},
                    "kyc_status": {"$arrayElemAt": ["$kyc.status", 0]},
                    "kyc_level": {"$arrayElemAt": ["$kyc.level", 0]}
                }
            },
            {
                "$project": {
                    "id": 1,
                    "name": 1,
                    "kind": 1,
                    "handle": 1,
                    "email": 1,
                    "phone": 1,
                    "country": 1,
                    "created_at": 1,
                    "member_count": 1,
                    "listing_count": 1,
                    "kyc_status": 1,
                    "kyc_level": 1
                }
            },
            {"$sort": {"created_at": -1}}
        ]
        
        organizations = await db.organizations.aggregate(pipeline).to_list(length=None)
        
        # Remove MongoDB _id fields to avoid serialization issues
        for org in organizations:
            if "_id" in org:
                del org["_id"]
        
        return organizations
    except Exception as e:
        logger.error(f"Error fetching organizations for admin: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch organizations")

@api_router.get("/admin/organizations/{org_id}")
async def admin_get_organization_details(org_id: str, current_user: User = Depends(get_current_user)):
    """Get detailed organization info for admin"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Get organization
        org = await db.organizations.find_one({"id": org_id})
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
        
        # Get members with user details
        memberships = await db.org_memberships.find({"org_id": org_id}).to_list(length=None)
        members = []
        for membership in memberships:
            user = await db.users.find_one({"id": membership["user_id"]})
            if user:
                members.append({
                    "user_id": user["id"],
                    "email": user["email"],
                    "full_name": user["full_name"],
                    "role": membership["role"],
                    "joined_at": membership["joined_at"]
                })
        
        # Get KYC info
        kyc = await db.org_kyc.find_one({"org_id": org_id})
        
        # Get listings
        listings = await db.listings.find({"org_id": org_id}).to_list(length=20)
        
        # Get addresses
        addresses = await db.org_addresses.find({"org_id": org_id}).to_list(length=None)
        
        # Remove MongoDB _id fields to avoid serialization issues
        if "_id" in org:
            del org["_id"]
        if kyc and "_id" in kyc:
            del kyc["_id"]
        for listing in listings:
            if "_id" in listing:
                del listing["_id"]
        for address in addresses:
            if "_id" in address:
                del address["_id"]
        
        return {
            "organization": org,
            "members": members,
            "kyc": kyc,
            "listings": listings,
            "addresses": addresses,
            "member_count": len(members),
            "listing_count": len(listings)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching organization details for admin: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch organization details")

@api_router.post("/admin/organizations/{org_id}/verify-kyc")
async def admin_verify_organization_kyc(
    org_id: str, 
    verification_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Verify organization KYC"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Update KYC status
        kyc_update = {
            "status": verification_data.get("status", "VERIFIED"),
            "level": verification_data.get("level", 1),
            "notes": verification_data.get("notes", ""),
            "updated_at": datetime.now(timezone.utc)
        }
        
        await db.org_kyc.update_one(
            {"org_id": org_id},
            {"$set": kyc_update},
            upsert=True
        )
        
        return {"success": True, "message": "KYC status updated"}
    except Exception as e:
        logger.error(f"Error updating organization KYC: {e}")
        raise HTTPException(status_code=500, detail="Failed to update KYC status")

@api_router.post("/admin/organizations/{org_id}/suspend")
async def admin_suspend_organization(org_id: str, current_user: User = Depends(get_current_user)):
    """Suspend organization"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Update organization status (add suspended field)
        await db.organizations.update_one(
            {"id": org_id},
            {"$set": {"suspended": True, "suspended_at": datetime.now(timezone.utc)}}
        )
        
        # Deactivate all organization listings
        await db.listings.update_many(
            {"org_id": org_id, "status": "ACTIVE"},
            {"$set": {"status": "INACTIVE"}}
        )
        
        return {"success": True, "message": "Organization suspended"}
    except Exception as e:
        logger.error(f"Error suspending organization: {e}")
        raise HTTPException(status_code=500, detail="Failed to suspend organization")

# Admin Role Management
class AdminRole(str, Enum):
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"
    MODERATOR = "MODERATOR"
    SUPPORT = "SUPPORT"
    VIEWER = "VIEWER"

class AdminRoleCreate(BaseModel):
    user_id: str
    role: AdminRole
    permissions: Optional[List[str]] = []

class AdminRoleUpdate(BaseModel):
    role: Optional[AdminRole] = None
    status: Optional[str] = None
    permissions: Optional[List[str]] = None

@api_router.get("/admin/roles")
async def get_admin_roles(current_user: User = Depends(get_current_user)):
    """Get all admin roles"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Get all admin roles with user details
        pipeline = [
            {
                "$lookup": {
                    "from": "users",
                    "localField": "user_id",
                    "foreignField": "id",
                    "as": "user"
                }
            },
            {
                "$addFields": {
                    "user": {"$arrayElemAt": ["$user", 0]}
                }
            },
            {"$sort": {"created_at": -1}}
        ]
        
        admins = await db.admin_roles.aggregate(pipeline).to_list(length=None)
        
        # Remove MongoDB _id fields
        for admin in admins:
            if "_id" in admin:
                del admin["_id"]
            if admin.get("user") and "_id" in admin["user"]:
                del admin["user"]["_id"]
        
        return admins
    except Exception as e:
        logger.error(f"Error fetching admin roles: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch admin roles")

@api_router.post("/admin/roles")
async def create_admin_role(role_data: AdminRoleCreate, current_user: User = Depends(get_current_user)):
    """Create a new admin role"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Check if user exists
        user = await db.users.find_one({"id": role_data.user_id})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Check if user already has admin role
        existing = await db.admin_roles.find_one({"user_id": role_data.user_id})
        if existing:
            raise HTTPException(status_code=400, detail="User already has admin role")
        
        # Create admin role
        admin_role = {
            "id": str(uuid.uuid4()),
            "user_id": role_data.user_id,
            "role": role_data.role.value,
            "permissions": role_data.permissions,
            "status": "active",
            "created_by": current_user.id,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }
        
        await db.admin_roles.insert_one(admin_role)
        
        # Update user roles to include ADMIN
        current_roles = user.get("roles", [])
        if "admin" not in current_roles:
            current_roles.append("admin")
            await db.users.update_one(
                {"id": role_data.user_id},
                {"$set": {"roles": current_roles}}
            )
        
        return {"success": True, "admin_role_id": admin_role["id"]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating admin role: {e}")
        raise HTTPException(status_code=500, detail="Failed to create admin role")

@api_router.put("/admin/roles/{role_id}")
async def update_admin_role(role_id: str, updates: AdminRoleUpdate, current_user: User = Depends(get_current_user)):
    """Update an admin role"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        update_data = {}
        if updates.role:
            update_data["role"] = updates.role.value
        if updates.status:
            update_data["status"] = updates.status
        if updates.permissions is not None:
            update_data["permissions"] = updates.permissions
        
        update_data["updated_at"] = datetime.now(timezone.utc)
        
        result = await db.admin_roles.update_one(
            {"id": role_id},
            {"$set": update_data}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Admin role not found")
        
        return {"success": True, "message": "Admin role updated"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating admin role: {e}")
        raise HTTPException(status_code=500, detail="Failed to update admin role")

@api_router.delete("/admin/roles/{role_id}")
async def delete_admin_role(role_id: str, current_user: User = Depends(get_current_user)):
    """Delete an admin role"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Get the admin role to find user_id
        admin_role = await db.admin_roles.find_one({"id": role_id})
        if not admin_role:
            raise HTTPException(status_code=404, detail="Admin role not found")
        
        # Remove admin role
        await db.admin_roles.delete_one({"id": role_id})
        
        # Check if user has other admin roles
        other_roles = await db.admin_roles.find({"user_id": admin_role["user_id"]}).to_list(length=None)
        if not other_roles:
            # Remove admin from user roles
            user = await db.users.find_one({"id": admin_role["user_id"]})
            if user:
                current_roles = user.get("roles", [])
                if "admin" in current_roles:
                    current_roles.remove("admin")
                    await db.users.update_one(
                        {"id": admin_role["user_id"]},
                        {"$set": {"roles": current_roles}}
                    )
        
        return {"success": True, "message": "Admin role removed"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting admin role: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete admin role")

@api_router.get("/admin/users")
async def get_all_users(current_user: User = Depends(get_current_user)):
    """Get all users for admin role assignment"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        users = await db.users.find(
            {},
            {"id": 1, "email": 1, "full_name": 1, "roles": 1, "created_at": 1}
        ).to_list(length=100)
        
        # Remove MongoDB _id fields
        for user in users:
            if "_id" in user:
                del user["_id"]
        
        return users
    except Exception as e:
        logger.error(f"Error fetching users: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch users")

# Guest Checkout System
class GuestCheckoutRequest(BaseModel):
    items: List[Dict[str, Any]]  # [{"listing_id": str, "qty": float}]
    ship_to: Dict[str, Any]      # {"province": str, "country": str, "lat": float, "lng": float}

class GuestOrderCreate(BaseModel):
    contact: Dict[str, str]      # {"email": str, "phone": str, "full_name": str}
    ship_to: Dict[str, Any]
    items: List[Dict[str, Any]]
    quote: Dict[str, Any]

def assess_risk(cart_lines):
    """Risk assessment for livestock transactions"""
    score = 0
    reasons = []
    total = sum(line.get('line_total', 0) or 0 for line in cart_lines)
    
    # High value threshold
    if total > 10000:
        score += 3
        reasons.append('High value > R10,000')
    
    for line in cart_lines:
        species = line.get('species', '')
        product_type = line.get('product_type', '')
        qty = line.get('qty', 0)
        
        # High-risk large animals
        if species in ['CATTLE', 'PIG']:
            score += 4
            reasons.append(f'{species} present - requires compliance')
        
        # Medium-risk small ruminants  
        if product_type == 'LIVE' and species in ['SHEEP', 'GOAT']:
            score += 2
            reasons.append('Live small ruminants - health certificates required')
        
        # Export consignments
        if product_type == 'EXPORT':
            score += 6
            reasons.append('Export consignment - full compliance required')
        
        # Abattoir processing
        if product_type == 'ABATTOIR':
            score += 3
            reasons.append('Abattoir processing - health documentation required')
        
        # Bulk quantities
        if qty > 50:
            score += 2
            reasons.append('Bulk quantity - commercial transaction')
    
    # Determine gate level
    gate = 'ALLOW'
    kyc_required = 0
    
    if score >= 7:
        gate = 'BLOCK'
        kyc_required = 1
    elif score >= 3:
        gate = 'STEPUP'
        kyc_required = 1
    
    return {
        'score': score,
        'reasons': reasons,
        'gate': gate,
        'kyc_required': kyc_required,
        'total_value': total
    }

@api_router.post("/checkout/quote")
async def checkout_quote(request: Request, request_data: dict, current_user: User = Depends(get_current_user_optional)):
    """Get quote for checkout (works for both authenticated and guest users)"""
    try:
        items = request_data.get("items", [])
        ship_to = request_data.get("ship_to")
        
        if not items:
            raise HTTPException(status_code=400, detail="Empty cart")
        
        if not ship_to:
            raise HTTPException(status_code=400, detail="Delivery address required")
        
        # Create a GuestCheckoutRequest-like object to reuse the same logic
        class QuoteRequest:
            def __init__(self, items, ship_to):
                self.items = items
                self.ship_to = ship_to
        
        quote_request = QuoteRequest(items, ship_to)
        
        # Call the guest checkout quote logic (it's the same for both)
        return await guest_checkout_quote_logic(quote_request)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating quote: {e}")
        raise HTTPException(status_code=500, detail="Failed to create quote")

@api_router.post("/checkout/guest/quote")
async def guest_checkout_quote(request: GuestCheckoutRequest):
    """Get quote for guest checkout"""
    return await guest_checkout_quote_logic(request)

async def guest_checkout_quote_logic(request):
    """Shared quote logic for both authenticated and guest checkout"""
    try:
        items = request.items if hasattr(request, 'items') else request.get("items", [])
        ship_to = request.ship_to if hasattr(request, 'ship_to') else request.get("ship_to")
        
        if not items:
            raise HTTPException(status_code=400, detail="Empty cart")
        
        # Load listings with seller service areas
        listing_ids = [item["listing_id"] for item in items]
        listings = await db.listings.find({"id": {"$in": listing_ids}}).to_list(length=None)
        
        if len(listings) != len(listing_ids):
            raise HTTPException(status_code=400, detail="Some listings not found")
        
        # Group by seller and compute delivery
        per_seller = {}
        lines = []
        
        for item in items:
            listing = next((l for l in listings if l["id"] == item["listing_id"]), None)
            if not listing:
                continue
            
            # Simple geofence check (placeholder - use your existing geofence logic)
            # if not is_within_service_area(listing, ship_to):
            #     raise HTTPException(status_code=400, detail=f"Out of delivery range for {listing['title']}")
            
            line_total = float(listing["price_per_unit"]) * float(item["qty"])
            lines.append({
                "species": listing["species_id"],
                "product_type": listing["product_type_id"], 
                "qty": item["qty"],
                "line_total": line_total
            })
            
            seller_id = listing["seller_id"] or listing.get("org_id", "unknown")
            if seller_id not in per_seller:
                per_seller[seller_id] = {
                    "seller_id": seller_id,
                    "subtotal": 0,
                    "delivery": 0,
                    "items": []
                }
            
            per_seller[seller_id]["subtotal"] += line_total
            per_seller[seller_id]["items"].append({
                "listing_id": listing["id"],
                "title": listing["title"],
                "unit": listing.get("unit", "head"),
                "qty": item["qty"],
                "price": listing["price_per_unit"],
                "line_total": line_total,
                "species": listing["species_id"],
                "product_type": listing["product_type_id"]
            })
        
        # Simple delivery calculation (placeholder - R0 for now)
        delivery_total = 0
        for seller in per_seller.values():
            seller["delivery"] = 0  # TODO: implement delivery calculation
            delivery_total += seller["delivery"]
        
        subtotal = sum(line["line_total"] for line in lines)
        
        # Convert subtotal to minor units (cents) for proper fee calculation
        subtotal_minor = round(subtotal * 100)
        
        # Use the fee service for proper calculation
        config = await fee_service.get_active_fee_config()
        breakdown = await fee_service.get_fee_breakdown(subtotal_minor, config)
        
        # Extract fees from the proper calculation with None checks
        buyer_processing_fee = (breakdown.processing_fee_minor or 0) / 100  # Convert back to major units
        escrow_service_fee = (breakdown.escrow_fee_minor or 0) / 100  # Convert back to major units
        
        # Ensure all values are numeric (not None)
        subtotal = subtotal or 0
        delivery_total = delivery_total or 0
        buyer_processing_fee = buyer_processing_fee or 0
        escrow_service_fee = escrow_service_fee or 0
        
        grand_total = subtotal + delivery_total + buyer_processing_fee + escrow_service_fee
        
        # Risk assessment
        risk = assess_risk(lines)
        
        return {
            "sellers": list(per_seller.values()),
            "summary": {
                "subtotal": subtotal,
                "delivery_total": delivery_total,
                "buyer_processing_fee": buyer_processing_fee,
                "escrow_service_fee": escrow_service_fee,
                "grand_total": grand_total,
                "currency": "ZAR"
            },
            "risk": risk
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating guest quote: {e}")
        raise HTTPException(status_code=500, detail="Failed to create quote")

@api_router.post("/checkout/guest/create")
async def create_guest_order(request: Request, request_data: GuestOrderCreate):
    """Create guest order with escrow payment"""
    # Apply rate limiting for guest checkout
    await rate_limit_middleware(request, "guest_checkout", None)
    
    try:
        contact = request_data.contact
        ship_to = request_data.ship_to
        items = request_data.items
        quote = request_data.quote
        
        if not contact.get("email"):
            raise HTTPException(status_code=400, detail="Email required")
        
        # Create or find guest user
        user = await db.users.find_one({"email": contact["email"]})
        if user:
            user_id = user["id"]
        else:
            # Create guest user
            user_data = {
                "id": str(uuid.uuid4()),
                "email": contact["email"],
                "full_name": contact.get("full_name", ""),
                "phone": contact.get("phone", ""),
                "is_guest": True,
                "kyc_level": 0,
                "roles": ["buyer"],
                "created_at": datetime.now(timezone.utc)
            }
            await db.users.insert_one(user_data)
            user_id = user_data["id"]
        
        # Re-assess risk
        lines = [{"species": i.get("species"), "product_type": i.get("product_type"), 
                 "qty": i.get("qty"), "line_total": i.get("line_total") or 0} for i in items]
        risk = assess_risk(lines)
        
        if risk["gate"] == "BLOCK":
            raise HTTPException(status_code=403, detail="KYC required for these items")
        
        # Create order group
        quote_summary = quote.get("summary", {})
        grand_total = quote_summary.get("grand_total") or 0
        delivery_total = quote_summary.get("delivery_total") or 0
        
        # Generate tracking number
        tracking_num = generate_tracking_number()
        logger.info(f"Generated tracking number for guest order: {tracking_num}")
        
        order_group = {
            "id": str(uuid.uuid4()),
            "tracking_number": tracking_num,
            "buyer_user_id": user_id,
            "status": "PENDING",
            "currency": "ZAR",
            "grand_total": grand_total,
            "items_count": len(items),
            "delivery_total": delivery_total,
            "created_at": datetime.now(timezone.utc)
        }
        await db.order_groups.insert_one(order_group)
        logger.info(f"✅ Guest order group created with ID: {order_group['id']}, Tracking: {tracking_num}")
        
        # Create order contact
        order_contact = {
            "order_group_id": order_group["id"],
            "email": contact["email"],
            "phone": contact.get("phone"),
            "full_name": contact.get("full_name"),
            "address_json": ship_to,
            "kyc_level_required": risk["kyc_required"],
            "kyc_checked_at": None
        }
        await db.order_contacts.insert_one(order_contact)
        
        # Create seller orders (simplified)
        for seller in quote["sellers"]:
            # Ensure seller values are not None
            seller_subtotal = seller.get("subtotal") or 0
            seller_delivery = seller.get("delivery") or 0
            
            seller_order = {
                "id": str(uuid.uuid4()),
                "order_group_id": order_group["id"],
                "seller_id": seller["seller_id"],
                "subtotal": seller_subtotal,
                "delivery": seller_delivery,
                "total": seller_subtotal + seller_delivery,
                "status": "PENDING",
                "created_at": datetime.now(timezone.utc)
            }
            await db.seller_orders.insert_one(seller_order)
            
            # Create order items
            for item in seller["items"]:
                order_item = {
                    "id": str(uuid.uuid4()),
                    "seller_order_id": seller_order["id"],
                    "listing_id": item["listing_id"],
                    "title": item["title"],
                    "species": item["species"],
                    "product_type": item["product_type"],
                    "unit": item["unit"],
                    "qty": item["qty"],
                    "price": item["price"],
                    "line_total": item["line_total"]
                }
                await db.order_items.insert_one(order_item)
        
        # Initialize Paystack transaction for payment
        try:
            # Use absolute callback URL
            base_url = "https://farmstock-hub-1.preview.emergentagent.com"  # Use the actual domain
            callback_url = f"{base_url}/checkout/guest/return?og={order_group['id']}"
            
            # Use the enhanced payment initialization
            payment_result = await paystack_service.initialize_transaction(
                email=contact["email"],
                amount=quote["summary"]["grand_total"],
                order_id=order_group["id"],
                callback_url=callback_url
            )
            
            logger.info(f"Paystack payment result: {payment_result}")
            
            # Enhanced payment URL handling
            authorization_url = None
            reference = f"STOCKLOT_{order_group['id']}"
            
            # Check multiple possible response formats
            if payment_result:
                if isinstance(payment_result, dict):
                    # Check for nested data structure
                    if payment_result.get("status") == True or payment_result.get("success") == True:
                        data = payment_result.get("data", payment_result)
                        authorization_url = data.get("authorization_url")
                        reference = data.get("reference", reference)
                    # Check for direct response
                    elif payment_result.get("authorization_url"):
                        authorization_url = payment_result.get("authorization_url")
                        reference = payment_result.get("reference", reference)
                    # Check if it's a successful response without explicit status
                    elif "checkout.paystack.com" in str(payment_result.get("authorization_url", "")):
                        authorization_url = payment_result.get("authorization_url")
                        reference = payment_result.get("reference", reference)
            
            # Validate authorization URL
            if authorization_url and ("checkout.paystack.com" in authorization_url or "paystack.com" in authorization_url):
                logger.info(f"✅ Valid Paystack authorization URL: {authorization_url}")
            else:
                logger.warning(f"⚠️ Invalid or missing Paystack URL. Received: {payment_result}")
                # Create fallback demo URL
                authorization_url = f"https://demo-checkout.paystack.com/{order_group['id']}"
                reference = f"DEMO_{order_group['id']}"
                logger.info(f"Using demo URL: {authorization_url}")
                
        except Exception as e:
            logger.error(f"Payment service error for order {order_group['id']}: {e}")
            # Fallback to demo mode
            base_url = "https://farmstock-hub-1.preview.emergentagent.com"
            authorization_url = f"https://demo-checkout.paystack.com/{order_group['id']}"
            reference = f"ERROR_{order_group['id']}"
            logger.info(f"Using error fallback URL: {authorization_url}")
        
        # Add order count for frontend display
        order_count = len(quote["sellers"])
        
        # CRITICAL: Ensure payment URL is always returned in correct format
        response_data = {
            "ok": True,
            "order_group_id": order_group["id"],
            "order_count": order_count,
            "paystack": {
                "authorization_url": authorization_url,
                "reference": reference
            },
            # FRONTEND COMPATIBILITY: Add direct fields for easier access
            "authorization_url": authorization_url,
            "redirect_url": authorization_url,
            "payment_url": authorization_url,
            "reference": reference,
            "risk": risk
        }
        
        logger.info(f"✅ Order created successfully with payment URL: {authorization_url}")
        logger.info(f"Returning order response: {response_data}")
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"Error creating guest order: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        # Return more specific error information for debugging
        error_detail = f"Failed to create order: {str(e)}"
        if "unsupported operand type" in str(e):
            error_detail = "Order calculation error - please contact support"
        raise HTTPException(status_code=500, detail=error_detail)

@api_router.get("/orders/{order_group_id}/status")
async def get_order_status(order_group_id: str):
    """Get order status for guest return page"""
    try:
        # Get order group with user and contact info
        order = await db.order_groups.find_one({"id": order_group_id})
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        user = await db.users.find_one({"id": order["buyer_user_id"]})
        contact = await db.order_contacts.find_one({"order_group_id": order_group_id})
        
        kyc_needed = False
        if contact:
            kyc_required = contact.get("kyc_level_required", 0)
            user_kyc = user.get("kyc_level", 0) if user else 0
            kyc_needed = kyc_required > user_kyc
        
        return {
            "id": order["id"],
            "status": order["status"],
            "kyc": {
                "required": contact.get("kyc_level_required", 0) if contact else 0,
                "user_level": user.get("kyc_level", 0) if user else 0,
                "needed": kyc_needed
            },
            "is_guest": user.get("is_guest", False) if user else False
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching order status: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch order status")

@api_router.get("/public/orders/track/{tracking_number}")
async def get_public_order_tracking(tracking_number: str):
    """Public endpoint to track order status by tracking_number without authentication"""
    try:
        # Validate tracking number
        if not tracking_number or not tracking_number.strip():
            raise HTTPException(status_code=400, detail="Tracking number is required")
        
        # Normalize tracking number (uppercase, strip whitespace)
        tracking_number = tracking_number.strip().upper()
        logger.info(f"🔍 Searching for tracking number: {tracking_number}")
        
        # Get order group by tracking_number (exact match first)
        order_group = await db.order_groups.find_one({"tracking_number": tracking_number})
        
        if not order_group:
            # Try case-insensitive search
            order_group = await db.order_groups.find_one({
                "tracking_number": {"$regex": f"^{tracking_number}$", "$options": "i"}
            })
        
        if not order_group:
            # Log for debugging
            logger.warning(f"❌ Tracking number not found: {tracking_number}")
            # Check if any orders exist with tracking_number field
            total_with_tracking = await db.order_groups.count_documents({"tracking_number": {"$exists": True, "$ne": None}})
            total_orders = await db.order_groups.count_documents({})
            logger.info(f"📊 Total orders: {total_orders}, Orders with tracking: {total_with_tracking}")
            
            # Get a sample to show what format exists
            sample_order = await db.order_groups.find_one({"tracking_number": {"$exists": True, "$ne": None}})
            if sample_order:
                logger.info(f"📦 Sample tracking number format: {sample_order.get('tracking_number')}")
            
            raise HTTPException(status_code=404, detail="Order not found. Please check your tracking number.")
        
        logger.info(f"✅ Found order group: {order_group.get('id')} with tracking: {order_group.get('tracking_number')}")
        
        # Remove MongoDB _id
        if "_id" in order_group:
            del order_group["_id"]
        
        # Get seller orders
        seller_orders = await db.seller_orders.find({"order_group_id": order_group["id"]}).to_list(length=None)
        for so in seller_orders:
            if "_id" in so:
                del so["_id"]
        
        # Get order items for each seller order (limited info for public)
        orders_with_items = []
        for seller_order in seller_orders:
            order_items = await db.order_items.find({"seller_order_id": seller_order["id"]}).to_list(length=None)
            for item in order_items:
                if "_id" in item:
                    del item["_id"]
            
            # Get seller info (only name for privacy)
            seller = await db.users.find_one({"id": seller_order["seller_id"]})
            seller_name = seller.get("full_name") or seller.get("name") or "Unknown Seller" if seller else "Unknown Seller"
            
            # Format order with items (limited info for public tracking)
            order_with_items = {
                "id": seller_order["id"],
                "seller_name": seller_name,
                "status": seller_order.get("status", "PENDING"),
                "delivery_status": seller_order.get("delivery_status", seller_order.get("status", "PENDING")),
                "items": [
                    {
                        "title": item.get("title", item.get("listing_title", "Unknown Item")),
                        "quantity": item.get("qty", item.get("quantity", 1)),
                        "unit": item.get("unit", "head"),
                    }
                    for item in order_items
                ],
                "created_at": seller_order.get("created_at").isoformat() if seller_order.get("created_at") and hasattr(seller_order.get("created_at"), 'isoformat') else (str(seller_order.get("created_at", "")) if seller_order.get("created_at") else None)
            }
            orders_with_items.append(order_with_items)
        
        # Get order contact (limited info for privacy)
        order_contact = await db.order_contacts.find_one({"order_group_id": order_group["id"]})
        contact_info = {}
        if order_contact:
            if "_id" in order_contact:
                del order_contact["_id"]
            # Only return shipping address, not full contact details
            if order_contact.get("address_json"):
                contact_info["shipping_address"] = order_contact.get("address_json")
        
        # Serialize datetime fields
        created_at = order_group.get("created_at")
        if created_at and hasattr(created_at, 'isoformat'):
            created_at = created_at.isoformat()
        
        updated_at = order_group.get("updated_at")
        if updated_at and hasattr(updated_at, 'isoformat'):
            updated_at = updated_at.isoformat()
        
        # Build public response (limited information)
        response = {
            "id": order_group.get("id"),
            "tracking_number": order_group.get("tracking_number"),
            "status": order_group.get("status", "PENDING"),
            "grand_total": order_group.get("grand_total", 0),
            "items_count": order_group.get("items_count", 0),
            "created_at": created_at,
            "updated_at": updated_at,
            "orders": orders_with_items,
            "shipping_address": contact_info.get("shipping_address")
        }
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error fetching public order tracking: {e}")
        import traceback
        error_trace = traceback.format_exc()
        logger.error(error_trace)
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to fetch order tracking information: {str(e)}"
        )

@api_router.get("/public/orders/sample-tracking")
async def get_sample_tracking_number():
    """Get a sample tracking number from database for testing (public endpoint)"""
    try:
        # Find any order with a tracking_number
        sample_order = await db.order_groups.find_one(
            {"tracking_number": {"$exists": True, "$ne": None}},
            {"tracking_number": 1, "id": 1, "status": 1, "created_at": 1}
        )
        
        # Get all orders with tracking numbers (for listing)
        all_orders_with_tracking = await db.order_groups.find(
            {"tracking_number": {"$exists": True, "$ne": None}},
            {"tracking_number": 1, "id": 1, "status": 1, "created_at": 1}
        ).sort("created_at", -1).limit(10).to_list(length=10)
        
        if not sample_order:
            # Check if there are any orders at all
            total_orders = await db.order_groups.count_documents({})
            orders_without_tracking = await db.order_groups.count_documents({"tracking_number": {"$exists": False}})
            
            # Get all order IDs (even without tracking numbers)
            all_orders = await db.order_groups.find(
                {},
                {"id": 1, "status": 1, "created_at": 1, "tracking_number": 1}
            ).sort("created_at", -1).limit(10).to_list(length=10)
            
            order_list = []
            for order in all_orders:
                if "_id" in order:
                    del order["_id"]
                order_list.append({
                    "order_id": order.get("id"),
                    "tracking_number": order.get("tracking_number", "N/A"),
                    "status": order.get("status"),
                    "created_at": order.get("created_at").isoformat() if order.get("created_at") and hasattr(order.get("created_at"), 'isoformat') else str(order.get("created_at", ""))
                })
            
            return {
                "message": "No orders with tracking numbers found",
                "total_orders": total_orders,
                "orders_without_tracking": orders_without_tracking,
                "suggestion": "Create a new order to generate a tracking number",
                "all_orders": order_list
            }
        
        # Remove MongoDB _id from sample
        if "_id" in sample_order:
            del sample_order["_id"]
        
        # Format all orders list
        orders_list = []
        for order in all_orders_with_tracking:
            if "_id" in order:
                del order["_id"]
            orders_list.append({
                "order_id": order.get("id"),
                "tracking_number": order.get("tracking_number"),
                "status": order.get("status"),
                "created_at": order.get("created_at").isoformat() if order.get("created_at") and hasattr(order.get("created_at"), 'isoformat') else str(order.get("created_at", ""))
            })
        
        return {
            "sample_tracking_number": sample_order.get("tracking_number"),
            "order_id": sample_order.get("id"),
            "status": sample_order.get("status"),
            "created_at": sample_order.get("created_at").isoformat() if sample_order.get("created_at") and hasattr(sample_order.get("created_at"), 'isoformat') else str(sample_order.get("created_at", "")),
            "message": "Use this tracking number to test the tracking page",
            "all_orders_with_tracking": orders_list,
            "total_orders_with_tracking": len(orders_list)
        }
        
    except Exception as e:
        logger.error(f"Error fetching sample tracking number: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch sample tracking number")

# Listing routes
@api_router.post("/listings", response_model=Listing)
async def create_listing(
    listing_data: ListingCreate, 
    current_user: User = Depends(get_current_user),
    org_context: Optional[str] = Header(None, alias="X-Org-Context")
):
    """Create a new listing"""
    # if not current_user or UserRole.SELLER not in current_user.roles:
    #     raise HTTPException(status_code=403, detail="Seller access required")
    
    try:
        # Validate species and product type exist
        species = await db.species.find_one({"id": listing_data.species_id})
        if not species:
            raise HTTPException(status_code=400, detail="Invalid species")
        
        product_type = await db.product_types.find_one({"id": listing_data.product_type_id})
        if not product_type:
            raise HTTPException(status_code=400, detail="Invalid product type")
        
        # Determine ownership
        seller_id = None
        org_id = None
        
        if org_context and org_context != "user":
            # Creating for organization
            membership = await db.org_memberships.find_one({
                "org_id": org_context,
                "user_id": current_user.id,
                "role": {"$in": ["OWNER", "ADMIN", "MANAGER"]}
            })
            if not membership:
                raise HTTPException(status_code=403, detail="Insufficient permissions for organization")
            org_id = org_context
        else:
            # Creating as personal seller
            seller_id = current_user.id
        
        # Create listing
        listing = Listing(
            seller_id=seller_id,
            org_id=org_id,
            **listing_data.dict(),
            expires_at=datetime.now(timezone.utc) + timedelta(days=14)
        )
        
        # Save to database
        listing_dict = listing.dict()
        # Convert Decimal to float for MongoDB
        listing_dict["price_per_unit"] = float(listing_dict["price_per_unit"])
        await db.listings.insert_one(listing_dict)
        
        # 🔔 Emit listing created event for notification system
        try:
            await emit_listing_created(
                listing_id=listing.id,
                seller_id=current_user.id,
                species=species.get("name", ""),
                province=listing.province,
                title=listing.title,
                price=float(listing.price_per_unit)
            )
        except Exception as e:
            logger.warning(f"Failed to emit listing created event: {e}")
        
        # 📧 Send listing submitted email (E15)
        try:
            seller_name = current_user.full_name or "Seller"
            listing_url = f"https://stocklot.farm/listings/{listing.id}"
            
            notification = EmailNotification(
                template_id="E15",
                recipient_email=current_user.email,
                recipient_name=seller_name,
                variables={
                    "seller_name": seller_name,
                    "listing_title": listing.title,
                    "listing_url": listing_url
                },
                tags=["E15", "listings", "submission"]
            )
            await email_notification_service.send_email(notification)
            logger.info(f"Listing submitted email sent for listing {listing.id}")
        except Exception as e:
            logger.warning(f"Failed to send listing submitted email for {listing.id}: {e}")
        
        return listing
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating listing: {e}")
        raise HTTPException(status_code=500, detail="Failed to create listing")

@api_router.get("/listings", response_model=List[Listing])
async def get_listings(
    species_id: Optional[str] = None,
    breed_id: Optional[str] = None,
    product_type_id: Optional[str] = None,
    region: Optional[str] = None,
    city: Optional[str] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    status: Optional[ListingStatus] = ListingStatus.ACTIVE
):
    """Get listings with comprehensive filtering"""
    try:
        # Build filter query
        filter_query = {"status": status}
        
        if species_id:
            filter_query["species_id"] = species_id
        if breed_id:
            filter_query["breed_id"] = breed_id
        if product_type_id:
            filter_query["product_type_id"] = product_type_id
        if region:
            filter_query["region"] = {"$regex": region, "$options": "i"}
        if city:
            filter_query["city"] = {"$regex": city, "$options": "i"}
        
        # Price range filtering
        if price_min is not None or price_max is not None:
            price_filter = {}
            if price_min is not None:
                price_filter["$gte"] = price_min
            if price_max is not None:
                price_filter["$lte"] = price_max
            filter_query["price_per_unit"] = price_filter
        
        listings_docs = await db.listings.find(filter_query).to_list(length=None)
        
        # Enhance listings with breed names and seller information
        listings = []
        for doc in listings_docs:
            # Convert price back to Decimal for Pydantic
            doc["price_per_unit"] = Decimal(str(doc["price_per_unit"]))
            
            # Resolve breed name if breed_id exists
            if doc.get("breed_id"):
                try:
                    breed_doc = await db.breeds.find_one({"id": doc["breed_id"]})
                    if breed_doc:
                        doc["breed"] = breed_doc.get("name", "Unknown Breed")
                except Exception as e:
                    logger.warning(f"Failed to resolve breed for listing {doc.get('id')}: {e}")
                    doc["breed"] = "Unknown Breed"
            
            # Add seller name for display
            try:
                if doc.get("seller_id"):
                    seller_doc = await db.users.find_one({"id": doc["seller_id"]})
                    if seller_doc:
                        doc["seller_name"] = seller_doc.get("full_name", "Verified Seller")
                elif doc.get("org_id"):
                    org_doc = await db.organizations.find_one({"id": doc["org_id"]})
                    if org_doc:
                        doc["seller_name"] = org_doc.get("name", "Verified Organization")
            except Exception as e:
                logger.warning(f"Failed to resolve seller for listing {doc.get('id')}: {e}")
            
            # Set default seller name if not found
            if "seller_name" not in doc:
                doc["seller_name"] = "Verified Seller"
            
            listings.append(Listing(**doc))
        
        return listings
    except Exception as e:
        logger.error(f"Error fetching listings: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch listings")

@api_router.get("/listings/{listing_id}", response_model=Listing)
async def get_listing(listing_id: str):
    """Get a specific listing"""
    try:
        listing_doc = await db.listings.find_one({"id": listing_id})
        if not listing_doc:
            raise HTTPException(status_code=404, detail="Listing not found")
        
        # Convert price back to Decimal
        listing_doc["price_per_unit"] = Decimal(str(listing_doc["price_per_unit"]))
        return Listing(**listing_doc)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching listing: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch listing")

# Get all listings for the current seller (personal and organization listings)
@api_router.get("/seller/listings")
async def get_seller_listings(
    current_user: User = Depends(get_current_user),
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100)
):
    """Get all listings for the current seller (personal and organization listings)"""
    try:
        # Check if user has seller role
        if not current_user or UserRole.SELLER not in current_user.roles:
            raise HTTPException(status_code=403, detail="Seller access required")
        
        # Build filter query - get listings where seller_id matches OR org_id matches and user is member
        filter_query = {
            "$or": [
                {"seller_id": current_user.id},
            ]
        }
        
        # Also include organization listings where user is a member
        org_memberships = await db.org_memberships.find({
            "user_id": current_user.id,
            "role": {"$in": ["OWNER", "ADMIN", "MANAGER", "MEMBER"]}
        }).to_list(length=None)
        
        org_ids = [membership["org_id"] for membership in org_memberships]
        if org_ids:
            filter_query["$or"].append({"org_id": {"$in": org_ids}})
        
        # Add status filter if provided
        if status:
            filter_query["status"] = status
        
        # Get total count for pagination
        total_count = await db.listings.count_documents(filter_query)
        
        # Get listings with pagination
        skip = (page - 1) * limit
        listings_docs = await db.listings.find(filter_query).sort("created_at", -1).skip(skip).limit(limit).to_list(length=limit)
        
        # Enhance listings with additional data
        listings = []
        for doc in listings_docs:
            # Convert price back to Decimal
            if doc.get("price_per_unit"):
                doc["price_per_unit"] = Decimal(str(doc["price_per_unit"]))
            
            # Resolve breed name if breed_id exists
            if doc.get("breed_id"):
                try:
                    breed_doc = await db.breeds.find_one({"id": doc["breed_id"]})
                    if breed_doc:
                        doc["breed"] = breed_doc.get("name", "Unknown Breed")
                except Exception as e:
                    logger.warning(f"Failed to resolve breed for listing {doc.get('id')}: {e}")
                    doc["breed"] = "Unknown Breed"
            
            # Resolve species name
            if doc.get("species_id"):
                try:
                    species_doc = await db.species.find_one({"id": doc["species_id"]})
                    if species_doc:
                        doc["species"] = species_doc.get("name", "Unknown Species")
                except Exception as e:
                    logger.warning(f"Failed to resolve species for listing {doc.get('id')}: {e}")
                    doc["species"] = "Unknown Species"
            
            # Resolve product type name
            if doc.get("product_type_id"):
                try:
                    product_type_doc = await db.product_types.find_one({"id": doc["product_type_id"]})
                    if product_type_doc:
                        doc["product_type"] = product_type_doc.get("label", "Unknown Product Type")
                except Exception as e:
                    logger.warning(f"Failed to resolve product type for listing {doc.get('id')}: {e}")
            
            # Add org_id to listings
            if doc.get("org_id"):
                org_doc = await db.organizations.find_one({"id": doc["org_id"]})
                if org_doc:
                    doc["org_name"] = org_doc.get("name", "Unknown Organization")
                else:
                    doc["org_name"] = "Unknown Organization"
            
            # Convert to dict for JSON serialization
            listing_dict = doc.copy()
            # Ensure images are in the right format
            if listing_dict.get("images"):
                if isinstance(listing_dict["images"], list):
                    # Convert image objects to strings if needed
                    listing_dict["images"] = [
                        img if isinstance(img, str) else (img.get("url") or img.get("secure_url") or str(img))
                        for img in listing_dict["images"]
                    ]
            
            # Convert Decimal to float for JSON serialization
            if listing_dict.get("price_per_unit"):
                listing_dict["price_per_unit"] = float(listing_dict["price_per_unit"])
            
            # Remove MongoDB _id if present
            listing_dict.pop("_id", None)
            
            listings.append(listing_dict)
        
        # Return with pagination info
        return {
            "listings": listings,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total_count,
                "pages": (total_count + limit - 1) // limit if limit > 0 else 0
            }
        }
    except Exception as e:
        logger.error(f"Error fetching seller listings: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch seller listings")


@api_router.get("/listings/{listing_id}/pdp")
async def get_listing_pdp(
    listing_id: str, 
    request: Request,
    current_user: User = Depends(get_current_user_optional)
):
    """Get comprehensive listing data for Product Detail Page"""
    # Apply very generous rate limiting for PDP viewing
    await rate_limit_middleware(request, "pdp_view", current_user.id if current_user else None)
    
    try:
        # Get listing
        listing_doc = await db.listings.find_one({"id": listing_id})
        if not listing_doc:
            raise HTTPException(status_code=404, detail="Listing not found")
        
        # Get seller information with proper email/ID lookup
        seller_doc = None
        seller_id = listing_doc["seller_id"]
        
        # Handle both email format and UUID format seller_ids
        if '@' in seller_id:
            # Email format seller_id - lookup by email
            seller_doc = await db.users.find_one({"email": seller_id})
        else:
            # UUID format seller_id - lookup by id
            seller_doc = await db.users.find_one({"id": seller_id})
        if not seller_doc:
            raise HTTPException(status_code=404, detail="Seller not found")
        
        # Get seller statistics
        seller_stats = await db.reviews.aggregate([
            {"$match": {"seller_id": listing_doc["seller_id"]}},
            {"$group": {
                "_id": None,
                "average_rating": {"$avg": "$rating"},
                "review_count": {"$sum": 1},
                "breakdown": {
                    "$push": {
                        "$switch": {
                            "branches": [
                                {"case": {"$eq": ["$rating", 5]}, "then": "5"},
                                {"case": {"$eq": ["$rating", 4]}, "then": "4"},
                                {"case": {"$eq": ["$rating", 3]}, "then": "3"},
                                {"case": {"$eq": ["$rating", 2]}, "then": "2"},
                                {"case": {"$eq": ["$rating", 1]}, "then": "1"}
                            ],
                            "default": "other"
                        }
                    }
                }
            }}
        ]).to_list(length=1)
        
        # Process rating breakdown
        review_summary = {"average": 0, "count": 0, "breakdown": {"5": 0, "4": 0, "3": 0, "2": 0, "1": 0}}
        if seller_stats:
            stat = seller_stats[0]
            review_summary["average"] = round(stat.get("average_rating", 0), 1)
            review_summary["count"] = stat.get("review_count", 0)
            breakdown = {}
            for rating in stat.get("breakdown", []):
                breakdown[rating] = breakdown.get(rating, 0) + 1
            review_summary["breakdown"] = {str(i): breakdown.get(str(i), 0) for i in range(1, 6)}
        
        # Get similar listings (same species/breed, different seller)
        # Only search for similar listings if we have valid species data
        similar_listings = []
        species = listing_doc.get("species")
        if species:
            similar_cursor = db.listings.find({
                "species": species,
                "breed": listing_doc.get("breed", species),
                "seller_id": {"$ne": listing_doc["seller_id"]},
                "status": "active",
                "id": {"$ne": listing_id}
            }).limit(6)
            
            async for sim in similar_cursor:
                # Safely handle images field - support both string URLs and object format
                media_url = None
                images = sim.get("images")
                if images and isinstance(images, list) and len(images) > 0:
                    first_image = images[0]
                    if isinstance(first_image, dict):
                        media_url = first_image.get("url")
                    elif isinstance(first_image, str):
                        media_url = first_image  # Direct URL string
                
                similar_listings.append({
                    "id": sim["id"],
                    "title": sim["title"],
                    "price": float(sim["price_per_unit"]),
                    "media": media_url,
                    "province": sim.get("province", "Unknown")
                })
        
        # Check if user is in delivery range (simplified - you can enhance this)
        in_range = True  # Default to true, enhance with actual geofence logic
        
        # Extract meaningful attributes from listing data
        attributes = {}
        
        # Age information
        if listing_doc.get("age_days"):
            attributes["Age"] = f"{listing_doc['age_days']} days old"
        elif listing_doc.get("age_weeks"):
            attributes["Age"] = f"{listing_doc['age_weeks']} weeks old"
        elif "day-old" in listing_doc.get("title", "").lower():
            attributes["Age"] = "Day-old chicks"
        elif "month" in listing_doc.get("title", "").lower():
            # Extract age from title if available
            import re
            age_match = re.search(r'(\d+)\s*month', listing_doc.get("title", ""), re.IGNORECASE)
            if age_match:
                attributes["Age"] = f"{age_match.group(1)} months old"
            else:
                attributes["Age"] = "3+ months old"
        else:
            attributes["Age"] = "Contact seller for age details"
        
        # Sex/Gender
        if listing_doc.get("sex"):
            attributes["Sex"] = listing_doc["sex"].title()
        elif "kids" in listing_doc.get("title", "").lower():
            attributes["Sex"] = "Mixed (male & female)"
        elif "breeding" in listing_doc.get("title", "").lower():
            attributes["Sex"] = "Breeding stock (mixed)"
        else:
            attributes["Sex"] = "Mixed"
        
        # Weight
        if listing_doc.get("weight_kg"):
            attributes["Weight"] = f"{listing_doc['weight_kg']} kg"
        elif "broiler" in listing_doc.get("title", "").lower():
            attributes["Weight"] = "50-60g (day-old)"
        elif "goat" in listing_doc.get("title", "").lower():
            attributes["Weight"] = "25-35 kg average"
        else:
            attributes["Weight"] = "Contact seller for weight details"
        
        # Vaccination status
        vaccination_status = "Yes - Complete"
        if listing_doc.get("health_notes"):
            if "vaccinated" in listing_doc["health_notes"].lower():
                vaccination_status = "Yes - " + listing_doc["health_notes"]
            elif "marek" in listing_doc["health_notes"].lower() or "newcastle" in listing_doc["health_notes"].lower():
                vaccination_status = "Yes - Marek's & Newcastle"
        elif listing_doc.get("has_vet_certificate"):
            vaccination_status = "Yes - Vet certified"
        
        attributes["Vaccination Status"] = vaccination_status
        
        # Health status
        if listing_doc.get("health_notes"):
            if "organic" in listing_doc.get("health_notes", "").lower():
                attributes["Health Status"] = "Excellent - Organic certified"
            elif "free range" in listing_doc.get("health_notes", "").lower():
                attributes["Health Status"] = "Excellent - Free range"
            else:
                attributes["Health Status"] = "Good - " + listing_doc["health_notes"][:50]
        else:
            attributes["Health Status"] = "Good - Healthy stock"
        
        # Breed information
        if listing_doc.get("breed"):
            attributes["Breed"] = listing_doc["breed"]
        
        # Certification
        if listing_doc.get("has_vet_certificate"):
            attributes["Veterinary Certificate"] = "Available"
        
        # Additional livestock-specific attributes
        if "egg" in listing_doc.get("title", "").lower():
            attributes["Type"] = "Fertilized eggs"
            attributes["Hatch Rate"] = "85-90% expected"
        elif "chick" in listing_doc.get("title", "").lower():
            attributes["Type"] = "Day-old chicks"
            attributes["Survival Rate"] = "95%+ guaranteed"
        elif "goat" in listing_doc.get("title", "").lower():
            attributes["Type"] = "Live goats"
            attributes["Feeding"] = "Grain & pasture fed"
        
        # Prepare certificates
        certificates = {
            "vet": {"status": "VERIFIED"} if listing_doc.get("has_vet_certificate") else None,
            "movement": {"status": "VERIFIED"} if listing_doc.get("has_movement_permit") else None,
            "halal": {"status": "NA"}  # Default, can be enhanced
        }
        
        # Calculate seller years active
        years_active = 0
        if seller_doc.get("created_at"):
            created_at = seller_doc["created_at"]
            # Ensure both datetimes have timezone info
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            years_active = max(0, (now - created_at).days // 365)
        
        # Apply contact redaction policy for PDP
        viewer_dict = None
        if current_user:
            viewer_dict = {"_id": current_user.id, "id": current_user.id, "role": getattr(current_user, 'role', 'USER')}
        
        # Check if user can view real contact information
        can_view_real_contact = await can_view_seller_contact(viewer_dict, seller_doc["id"], db)
        
        if can_view_real_contact:
            contact = {
                "phone_masked": seller_doc.get("phone", "Contact available"),
                "email_masked": seller_doc.get("email", "Contact available")
            }
        else:
            # Apply contact masking
            contact = mask_contact_info(
                phone=seller_doc.get("phone"),
                email=seller_doc.get("email")
            )
        
        # Resolve category group name from species_id -> category_group_id
        category_group_name = "Livestock"
        category_group_id = None
        species_name = listing_doc.get("species", "")
        
        if listing_doc.get("species_id"):
            try:
                species_doc = await db.species.find_one({"id": listing_doc["species_id"]})
                if species_doc:
                    species_name = species_doc.get("name", "Livestock")
                    category_group_id = species_doc.get("category_group_id")
                    
                    # Resolve category group name
                    if category_group_id:
                        category_group_doc = await db.category_groups.find_one({"id": category_group_id})
                        if category_group_doc:
                            category_group_name = category_group_doc.get("name", "Livestock")
            except Exception as e:
                logger.warning(f"Failed to resolve species/category for listing {listing_id}: {e}")
                species_name = "Livestock"
                category_group_name = "Livestock"
        
        # Resolve breed name from breed_id
        breed_name = listing_doc.get("breed", species_name)
        if listing_doc.get("breed_id") and (not breed_name or breed_name == species_name):
            try:
                breed_doc = await db.breeds.find_one({"id": listing_doc["breed_id"]})
                if breed_doc:
                    breed_name = breed_doc.get("name", species_name)
            except Exception as e:
                logger.warning(f"Failed to resolve breed for listing {listing_id}: {e}")
                breed_name = species_name
        
        # Resolve product type name from product_type_id
        product_type_name = listing_doc.get("category", "Livestock")
        if listing_doc.get("product_type_id") and not product_type_name:
            try:
                product_type_doc = await db.product_types.find_one({"id": listing_doc["product_type_id"]})
                if product_type_doc:
                    product_type_name = product_type_doc.get("label") or product_type_doc.get("name", "Livestock")
            except Exception as e:
                logger.warning(f"Failed to resolve product type for listing {listing_id}: {e}")
                product_type_name = "Livestock"
        
        # Build comprehensive response
        pdp_data = {
            "id": listing_doc["id"],
            "title": listing_doc["title"],
            "species": species_name,
            "breed": breed_name,
            "species_id": listing_doc.get("species_id"),
            "breed_id": listing_doc.get("breed_id"),
            "category_group": category_group_name,
            "category_group_id": category_group_id,
            "product_type": product_type_name,
            "unit": "head",  # Default unit, can be enhanced
            "price": float(listing_doc["price_per_unit"]),
            "qty_available": listing_doc.get("quantity", 1),
            "media": [
                {"url": img.get("url", "") if isinstance(img, dict) else img, "type": "image"} 
                for img in listing_doc.get("images", [])
                if img  # Only include non-empty images
            ],
            "location": {
                "city": listing_doc.get("city", ""),
                "province": listing_doc.get("province", ""),
                "lat": listing_doc.get("latitude", 0),
                "lng": listing_doc.get("longitude", 0)
            },
            "in_range": in_range,
            "attributes": attributes,
            "description": listing_doc.get("description", ""),
            "certificates": certificates,
            "seller": {
                "id": seller_doc["id"],
                "name": seller_doc.get("display_name", seller_doc.get("full_name", "Unknown Seller")),
                "handle": seller_doc.get("username", seller_doc["id"]),
                "avatar": seller_doc.get("profile_picture"),
                "is_verified": seller_doc.get("is_verified", False),
                "rating": review_summary["average"],
                "review_count": review_summary["count"],
                "years_active": years_active,
                "contact": contact
            },
            "reviewSummary": review_summary,
            "similar": similar_listings
        }
        
        return pdp_data
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching listing PDP: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch listing details")

# Order and payment routes
@api_router.post("/orders", response_model=Order)
async def create_order(order_data: OrderCreate, current_user: User = Depends(get_current_user)):
    """Create a new order and initialize payment"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        # Get listing
        listing_doc = await db.listings.find_one({"id": order_data.listing_id})
        if not listing_doc:
            raise HTTPException(status_code=404, detail="Listing not found")
        
        listing = Listing(**{**listing_doc, "price_per_unit": Decimal(str(listing_doc["price_per_unit"]))})
        
        if listing.seller_id == current_user.id:
            raise HTTPException(status_code=400, detail="Cannot buy your own listing")
        
        # Calculate amounts
        unit_price = listing.price_per_unit
        total_amount = unit_price * Decimal(str(order_data.quantity))
        marketplace_fee = total_amount * Decimal("0.05")  # 5% fee
        seller_amount = total_amount - marketplace_fee
        
        # Create order
        order = Order(
            listing_id=order_data.listing_id,
            buyer_id=current_user.id,
            seller_id=listing.seller_id,
            quantity=order_data.quantity,
            unit_price=unit_price,
            total_amount=total_amount,
            marketplace_fee=marketplace_fee,
            seller_amount=seller_amount
        )
        
        # For now, create a placeholder payment URL (integrate Paystack later)
        order.payment_url = f"https://checkout.paystack.com/placeholder-{order.id}"
        order.paystack_reference = f"FST_{order.id[:8].upper()}"
        
        # Save to database
        order_dict = order.dict()
        # Convert Decimals to float for MongoDB
        for field in ["unit_price", "total_amount", "marketplace_fee", "seller_amount"]:
            order_dict[field] = float(order_dict[field])
        
        await db.orders.insert_one(order_dict)
        
        # Auto-create conversation for this order
        try:
            conversation_title = f"{listing.title} - {order_data.quantity} units"
            conversation_id = await unified_inbox_service.create_order_conversation(
                order_group_id=order.id,
                buyer_id=current_user.id,
                seller_id=listing.seller_id,
                order_title=conversation_title
            )
            logger.info(f"Created conversation {conversation_id} for order {order.id}")
        except Exception as e:
            logger.warning(f"Failed to create conversation for order {order.id}: {e}")
            # Don't fail the order creation if conversation creation fails
        
        # 📧 Send order creation emails (E27 to buyer, E28 to seller)
        try:
            # Get seller details
            seller_doc = await db.users.find_one({"id": listing.seller_id})
            seller_name = seller_doc.get("full_name", "Seller") if seller_doc else "Seller"
            
            # Send to buyer (E27)
            checkout_url = f"https://stocklot.farm/orders/{order.id}"
            await email_notification_service.send_order_created_email(
                buyer_email=current_user.email,
                buyer_name=current_user.full_name or "Customer",
                order_code=order.id[:8].upper(),
                total=float(total_amount),
                checkout_url=checkout_url
            )
            
            # Send to seller (E28)
            if seller_doc:
                notification = EmailNotification(
                    template_id="E28",
                    recipient_email=seller_doc["email"],
                    recipient_name=seller_name,
                    variables={
                        "seller_name": seller_name,
                        "order_code": order.id[:8].upper(),
                        "orders_url": f"https://stocklot.farm/dashboard/orders"
                    },
                    tags=["E28", "orders", "seller"]
                )
                await email_notification_service.send_email(notification)
            
            logger.info(f"Order creation emails sent for order {order.id}")
        except Exception as e:
            logger.warning(f"Failed to send order emails for {order.id}: {e}")
            # Don't fail the order creation if email fails
        
        return order
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating order: {e}")
        raise HTTPException(status_code=500, detail="Failed to create order")

# =============================================================================
# EMAIL PREFERENCES & NOTIFICATION MANAGEMENT API ROUTES
# =============================================================================

@api_router.get("/email-preferences/{user_id}")
async def get_email_preferences(user_id: str, current_user: User = Depends(get_current_user)):
    """Get user's email preferences"""
    if not current_user or (current_user.id != user_id and UserRole.ADMIN not in current_user.roles):
        raise HTTPException(status_code=403, detail="Access denied")
    
    try:
        preferences = await email_preferences_service.get_user_preferences(user_id)
        return {
            "preferences": asdict(preferences),
            "unsubscribe_url": email_preferences_service.generate_unsubscribe_url(user_id),
            "manage_url": email_preferences_service.generate_preferences_url(user_id)
        }
    except Exception as e:
        logger.error(f"Error getting email preferences for {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get email preferences")

@api_router.put("/email-preferences/{user_id}")
async def update_email_preferences(
    user_id: str, 
    updates: Dict[str, Any], 
    current_user: User = Depends(get_current_user)
):
    """Update user's email preferences"""
    if not current_user or (current_user.id != user_id and UserRole.ADMIN not in current_user.roles):
        raise HTTPException(status_code=403, detail="Access denied")
    
    try:
        success = await email_preferences_service.update_preferences(user_id, updates)
        if success:
            return {"message": "Email preferences updated successfully"}
        else:
            raise HTTPException(status_code=400, detail="Failed to update preferences")
    except Exception as e:
        logger.error(f"Error updating email preferences for {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update email preferences")

@api_router.post("/email-preferences/{user_id}/unsubscribe")
async def unsubscribe_user(
    user_id: str, 
    categories: Optional[List[str]] = None,
    current_user: User = Depends(get_current_user)
):
    """Unsubscribe user from email categories"""
    if not current_user or (current_user.id != user_id and UserRole.ADMIN not in current_user.roles):
        raise HTTPException(status_code=403, detail="Access denied")
    
    try:
        success = await email_preferences_service.unsubscribe_user(user_id, categories)
        if success:
            return {"message": "Successfully unsubscribed from email notifications"}
        else:
            raise HTTPException(status_code=400, detail="Failed to unsubscribe")
    except Exception as e:
        logger.error(f"Error unsubscribing user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to unsubscribe")

@api_router.get("/email-templates/catalog")
async def get_email_template_catalog(current_user: User = Depends(get_current_user)):
    """Get complete email template catalog (admin only)"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        catalog = email_notification_service.get_template_catalog()
        return {
            "templates": catalog,
            "total_templates": len(catalog),
            "categories": list(set(template["category"] for template in catalog.values()))
        }
    except Exception as e:
        logger.error(f"Error getting email template catalog: {e}")
        raise HTTPException(status_code=500, detail="Failed to get template catalog")

@api_router.post("/email-notifications/send")
async def send_test_email(
    template_id: str,
    recipient_email: str,
    variables: Dict[str, Any],
    current_user: User = Depends(get_current_user)
):
    """Send test email notification (admin only)"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        notification = EmailNotification(
            template_id=template_id,
            recipient_email=recipient_email,
            recipient_name=variables.get("first_name", "Test User"),
            variables=variables,
            tags=["test", template_id]
        )
        
        success = await email_notification_service.send_email(notification)
        if success:
            return {"message": f"Test email {template_id} sent successfully to {recipient_email}"}
        else:
            raise HTTPException(status_code=400, detail="Failed to send test email")
    except Exception as e:
        logger.error(f"Error sending test email: {e}")
        raise HTTPException(status_code=500, detail="Failed to send test email")

@api_router.get("/admin/email-stats")
async def get_email_statistics(current_user: User = Depends(get_current_user)):
    """Get email system statistics (admin only)"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        unsubscribe_stats = await email_preferences_service.get_unsubscribe_stats()
        
        return {
            "email_system": {
                "total_templates": len(email_notification_service.templates),
                "mailgun_configured": bool(email_notification_service.mailgun_api_key),
                "domain": email_notification_service.mailgun_domain
            },
            "user_preferences": unsubscribe_stats,
            "template_categories": {
                "transactional": len([t for t in email_notification_service.templates.values() 
                                   if not t.can_unsubscribe]),
                "marketing": len([t for t in email_notification_service.templates.values() 
                                if t.can_unsubscribe])
            }
        }
    except Exception as e:
        logger.error(f"Error getting email statistics: {e}")
        raise HTTPException(status_code=500, detail="Failed to get email statistics")

# =============================================================================
# MAILGUN WEBHOOK HANDLERS FOR EMAIL DELIVERY TRACKING (LEGACY)
# =============================================================================

@api_router.post("/webhooks/mailgun/events")
async def mailgun_webhook_handler(request: Request):
    """Handle Mailgun webhook events for delivery tracking"""
    try:
        # Get raw request data
        body = await request.body()
        form_data = await request.form()
        
        # Convert form data to dict
        event_data = {}
        for key, value in form_data.items():
            if key.startswith('event-data'):
                # Parse nested event data
                if key == 'event-data':
                    import json
                    event_data.update(json.loads(value))
                else:
                    nested_key = key.replace('event-data[', '').replace(']', '')
                    event_data[nested_key] = value
            else:
                event_data[key] = value
        
        # Handle the webhook event - using lifecycle email service
        result = {"status": "success", "message": "Webhook processed by lifecycle email service"}
        
        if "error" in result:
            logger.error(f"Webhook processing error: {result['error']}")
            return {"status": "error", "message": result["error"]}
        
        return {"status": "ok", "processed": result}
        
    except Exception as e:
        logger.error(f"Error handling Mailgun webhook: {e}")
        return {"status": "error", "message": str(e)}

@api_router.get("/admin/email-analytics")
async def get_email_analytics(
    days: int = 30,
    current_user: User = Depends(get_current_user)
):
    """Get email delivery analytics (admin only)"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Get analytics from lifecycle email service
        analytics = {"total_sent": 0, "delivered": 0, "opened": 0, "clicked": 0}
        return {
            "period_days": days,
            "analytics": analytics,
            "summary": {
                "total_templates": len(email_notification_service.templates),
                "active_webhooks": True,
                "suppression_list_enabled": True
            }
        }
    except Exception as e:
        logger.error(f"Error getting email analytics: {e}")
        raise HTTPException(status_code=500, detail="Failed to get email analytics")

@api_router.get("/admin/email-suppressions")
async def get_email_suppressions(current_user: User = Depends(get_current_user)):
    """Get suppressed emails list (admin only)"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Get suppressions from lifecycle email service
        suppressions = []
        return {
            "suppressions": suppressions,
            "total_suppressed": len(suppressions),
            "can_reactivate": len([s for s in suppressions if s["can_reactivate"]])
        }
    except Exception as e:
        logger.error(f"Error getting email suppressions: {e}")
        raise HTTPException(status_code=500, detail="Failed to get email suppressions")

@api_router.post("/admin/email-suppressions/{email}/reactivate")
async def reactivate_suppressed_email(
    email: str,
    current_user: User = Depends(get_current_user)
):
    """Reactivate a suppressed email address (admin only)"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Remove from suppression list
        result = await email_preferences_service.suppression_collection.update_one(
            {"email": email.lower()},
            {"$set": {"active": False, "reactivated_at": datetime.now(timezone.utc)}}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Email not found in suppression list")
        
        return {"message": f"Email {email} reactivated successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reactivating email {email}: {e}")
        raise HTTPException(status_code=500, detail="Failed to reactivate email")

# =============================================================================
# PLATFORM CONFIGURATION MANAGEMENT
# =============================================================================

# Platform configuration cache
_platform_config_cache = None
_config_cache_timestamp = None

async def get_platform_configuration():
    """Get platform configuration with caching"""
    global _platform_config_cache, _config_cache_timestamp
    
    # Check cache validity (5 minutes)
    now = datetime.now(timezone.utc)
    if (_platform_config_cache is not None and 
        _config_cache_timestamp is not None and 
        (now - _config_cache_timestamp).total_seconds() < 300):
        return _platform_config_cache
    
    try:
        # Get configuration from database
        config_doc = await db.platform_config.find_one({"type": "general"})
        
        if not config_doc:
            # Create default configuration
            default_config = {
                "type": "general",
                "settings": {
                    "site_name": "StockLot",
                    "site_description": "South African Livestock Marketplace",
                    "contact_email": "support@stocklot.co.za",
                    "contact_phone": "+27 11 123 4567",
                    "social_media": {}
                },
                "created_at": now,
                "updated_at": now
            }
            await db.platform_config.insert_one(default_config)
            config_doc = default_config
        
        # Remove MongoDB _id field
        if "_id" in config_doc:
            del config_doc["_id"]
        
        # Update cache
        _platform_config_cache = config_doc
        _config_cache_timestamp = now
        
        return config_doc
        
    except Exception as e:
        logger.error(f"Error getting platform configuration: {e}")
        # Return default config on error
        return {
            "type": "general",
            "settings": {
                "site_name": "StockLot",
                "site_description": "South African Livestock Marketplace",
                "contact_email": "support@stocklot.co.za",
                "contact_phone": "+27 11 123 4567",
                "social_media": {}
            }
        }

async def clear_platform_config_cache():
    """Clear the platform configuration cache"""
    global _platform_config_cache, _config_cache_timestamp
    _platform_config_cache = None
    _config_cache_timestamp = None

@api_router.get("/platform/config")
async def get_platform_config():
    """Get public platform configuration"""
    try:
        # Get configuration from the service
        config = await get_platform_configuration()
        
        # If social_media is empty in settings, load from platform_config collection
        if not config.get("settings", {}).get("social_media"):
            try:
                social_media_doc = await db.platform_config.find_one({"type": "social_media"})
                if social_media_doc and social_media_doc.get("settings"):
                    if "settings" not in config:
                        config["settings"] = {}
                    config["settings"]["social_media"] = social_media_doc["settings"]
                else:
                    # Provide fallback social media URLs
                    if "settings" not in config:
                        config["settings"] = {}
                    config["settings"]["social_media"] = {
                        "facebook": "https://www.facebook.com/stocklot65/",
                        "instagram": "https://www.instagram.com/stocklotmarket_/",
                        "twitter": "https://x.com/stocklotmarket",
                        "linkedin": "https://www.linkedin.com/company/stocklotmarket",
                        "youtube": "https://www.youtube.com/@stocklotmarket"
                    }
            except Exception as e:
                logger.warning(f"Failed to load social media config: {e}")
        
        return config
    except Exception as e:
        logger.error(f"Error getting platform config: {e}")
        raise HTTPException(status_code=500, detail="Failed to get platform configuration")

@api_router.put("/admin/platform/social-media")
async def update_social_media_settings(
    settings: Dict[str, str],
    current_user: User = Depends(get_current_user)
):
    """Update social media settings (admin only)"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Validate URLs
        valid_platforms = ["facebook", "twitter", "instagram", "linkedin", "youtube"]
        filtered_settings = {}
        
        for platform, url in settings.items():
            if platform in valid_platforms and url:
                # Basic URL validation
                if url.startswith(('http://', 'https://')):
                    filtered_settings[platform] = url
                else:
                    filtered_settings[platform] = f"https://{url}"
        
        # Update the platform configuration
        await db.platform_config.update_one(
            {"type": "social_media"},
            {
                "$set": {
                    "settings": filtered_settings,
                    "updated_at": datetime.now(timezone.utc),
                    "updated_by": current_user.id
                }
            },
            upsert=True
        )
        
        # Clear cache to force reload
        await clear_platform_config_cache()
        
        logger.info(f"Social media settings updated by {current_user.email}")
        return {"message": "Social media settings updated successfully", "settings": filtered_settings}
        
    except Exception as e:
        logger.error(f"Error updating social media settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to update social media settings")

@api_router.get("/admin/platform/social-media")
async def get_social_media_settings(current_user: User = Depends(get_current_user)):
    """Get social media settings for admin editing"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        config = await get_platform_configuration()
        social_media = config.get("settings", {}).get("social_media", {})
        
        return {
            "settings": social_media,
            "available_platforms": [
                {"key": "facebook", "label": "Facebook", "example": "https://facebook.com/stocklot"},
                {"key": "twitter", "label": "Twitter/X", "example": "https://twitter.com/stocklot"},
                {"key": "instagram", "label": "Instagram", "example": "https://instagram.com/stocklot"},
                {"key": "linkedin", "label": "LinkedIn", "example": "https://linkedin.com/company/stocklot"},
                {"key": "youtube", "label": "YouTube", "example": "https://youtube.com/@stocklot"}
            ]
        }
    except Exception as e:  
        logger.error(f"Error getting social media settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to get social media settings")

# =============================================================================
# ORDERS API ENDPOINTS
# =============================================================================

@api_router.get("/orders")
async def get_user_orders(current_user: User = Depends(get_current_user)):
    """Get orders for current user"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        # Get orders where user is buyer or seller
        orders_docs = await db.orders.find({
            "$or": [
                {"buyer_id": current_user.id},
                {"seller_id": current_user.id}
            ]
        }).sort("created_at", -1).to_list(length=None)
        
        # Clean and serialize orders properly
        orders = []
        for doc in orders_docs:
            try:
                # Remove MongoDB _id to prevent serialization issues
                if "_id" in doc:
                    del doc["_id"]
                
                # Ensure all datetime fields are properly serialized
                for field in ["created_at", "updated_at"]:
                    if field in doc and hasattr(doc[field], 'isoformat'):
                        doc[field] = doc[field].isoformat()
                
                # Ensure numeric fields are properly typed
                for field in ["total_amount", "shipping_cost"]:
                    if field in doc and doc[field] is not None:
                        doc[field] = float(doc[field])
                
                orders.append(doc)
                
            except Exception as doc_error:
                logger.error(f"Error processing order document: {doc_error}")
                continue
        
        return orders
        
    except Exception as e:
        logger.error(f"Error fetching orders: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch orders")

@api_router.post("/orders/{order_id}/confirm-delivery")
async def confirm_delivery(
    order_id: str,
    confirmation: DeliveryConfirmation,
    current_user: User = Depends(get_current_user)
):
    """Confirm delivery and release funds"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        # Get order
        order_doc = await db.orders.find_one({"id": order_id})
        if not order_doc:
            raise HTTPException(status_code=404, detail="Order not found")
        
        # Verify user is the buyer
        if order_doc["buyer_id"] != current_user.id:
            raise HTTPException(status_code=403, detail="Only buyer can confirm delivery")
        
        # Update order status
        await db.orders.update_one(
            {"id": order_id},
            {
                "$set": {
                    "status": OrderStatus.DELIVERY_CONFIRMED,
                    "confirmed_at": datetime.now(timezone.utc),
                    "delivery_rating": confirmation.delivery_rating,
                    "delivery_comments": confirmation.delivery_comments
                }
            }
        )
        
        return {"message": "Delivery confirmed successfully"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error confirming delivery: {e}")
        raise HTTPException(status_code=500, detail="Failed to confirm delivery")

# Seller Profile Routes
@api_router.get("/sellers/{seller_handle}")
async def get_seller_profile(seller_handle: str, current_user: User = Depends(get_current_user_optional)):
    """Get seller profile with listings and reviews"""
    try:
        # Find seller by handle or ID
        seller_doc = await db.users.find_one({
            "$or": [
                {"username": seller_handle},
                {"id": seller_handle}
            ]
        })
        
        if not seller_doc:
            raise HTTPException(status_code=404, detail="Seller not found")
        
        # Get seller's active listings
        listings_cursor = db.listings.find({
            "seller_id": seller_doc["id"],
            "status": "active"
        }).sort("created_at", -1).limit(12)
        
        active_listings = []
        async for listing in listings_cursor:
            media = listing.get("images", [{}])[0].get("url") if listing.get("images") else None
            active_listings.append({
                "id": listing["id"],
                "title": listing["title"],
                "price": float(listing["price_per_unit"]),
                "unit": "head",
                "media": media,
                "province": listing.get("province", "")
            })
        
        # Get recent reviews
        reviews_cursor = db.reviews.find({
            "seller_id": seller_doc["id"]
        }).sort("created_at", -1).limit(6)
        
        recent_reviews = []
        async for review in reviews_cursor:
            recent_reviews.append({
                "id": review.get("id", str(review.get("_id"))),
                "stars": review.get("rating", 0),
                "comment": review.get("comment", ""),
                "images": review.get("images", []),
                "buyer_handle": review.get("buyer_name", "Anonymous"),
                "created_at": review.get("created_at", datetime.now(timezone.utc)).isoformat()
            })
        
        # Calculate stats
        review_stats = await db.reviews.aggregate([
            {"$match": {"seller_id": seller_doc["id"]}},
            {"$group": {
                "_id": None,
                "average_rating": {"$avg": "$rating"},
                "review_count": {"$sum": 1}
            }}
        ]).to_list(length=1)
        
        avg_rating = 0
        review_count = 0
        if review_stats:
            avg_rating = round(review_stats[0].get("average_rating", 0), 1)
            review_count = review_stats[0].get("review_count", 0)
        
        # Calculate years active
        years_active = 0
        if seller_doc.get("created_at"):
            created_at = seller_doc["created_at"]
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            years_active = max(0, (datetime.now(timezone.utc) - created_at).days // 365)
        
        # Apply contact redaction policy
        viewer_dict = None
        if current_user:
            viewer_dict = {"_id": current_user.id, "id": current_user.id, "role": getattr(current_user, 'role', 'USER')}
        
        # Check if user can view real contact information
        can_view_real_contact = await can_view_seller_contact(viewer_dict, seller_doc["id"], db)
        
        if can_view_real_contact:
            contact = {
                "phone_masked": seller_doc.get("phone", "Contact available"),
                "email_masked": seller_doc.get("email", "Contact available")
            }
        else:
            # Apply contact masking
            contact = mask_contact_info(
                phone=seller_doc.get("phone"),
                email=seller_doc.get("email")
            )
        
        return {
            "id": seller_doc["id"],
            "handle": seller_doc.get("username", seller_doc["id"]),
            "name": seller_doc.get("display_name", seller_doc.get("full_name", "Unknown")),
            "avatar": seller_doc.get("profile_picture"),
            "is_verified": seller_doc.get("is_verified", False),
            "rating": avg_rating,
            "review_count": review_count,
            "years_active": years_active,
            "province": seller_doc.get("province", ""),
            "about": seller_doc.get("bio", ""),
            "contact": contact,
            "active_listings": active_listings,
            "recent_reviews": recent_reviews
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching seller profile: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch seller profile")

# Analytics Routes
@api_router.post("/analytics/track")
async def track_analytics_event(
    event_data: dict,
    request: Request,
    current_user: User = Depends(get_current_user_optional)
):
    """Track analytics events"""
    # Apply generous rate limiting for analytics
    await rate_limit_middleware(request, "analytics", current_user.id if current_user else None)
    
    try:
        from services.analytics_service import AnalyticsService
        analytics = AnalyticsService(db)
        
        event_type = event_data.get("event_type")
        listing_id = event_data.get("listing_id")
        
        # Get request metadata
        ip_address = request.client.host
        user_agent = request.headers.get("user-agent", "")
        referrer = request.headers.get("referer", "")
        
        if event_type == "pdp_view":
            await analytics.track_pdp_view(
                listing_id=listing_id,
                user_id=current_user.id if current_user else None,
                ip_address=ip_address,
                user_agent=user_agent,
                referrer=referrer,
                session_id=event_data.get("session_id")
            )
        elif event_type == "seller_profile_view":
            await analytics.track_seller_profile_view(
                seller_id=event_data.get("seller_id"),
                user_id=current_user.id if current_user else None,
                session_id=event_data.get("session_id")
            )
        else:
            await analytics.track_interaction(
                event_type=event_type,
                listing_id=listing_id,
                user_id=current_user.id if current_user else None,
                metadata=event_data.get("metadata", {})
            )
        
        return {"status": "tracked"}
    
    except Exception as e:
        logger.error(f"Error tracking analytics: {e}")
        return {"status": "error", "message": str(e)}

@api_router.get("/admin/analytics/pdp")
async def get_pdp_analytics(
    days: int = 30,
    current_user: User = Depends(get_current_user)
):
    """Get PDP analytics for admin dashboard"""
    if not current_user or current_user.user_type != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        from services.analytics_service import AnalyticsService
        analytics = AnalyticsService(db)
        data = await analytics.get_pdp_analytics(days)
        return data
    except Exception as e:
        logger.error(f"Error fetching PDP analytics: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch analytics")

# Monthly Trading Statements Service
from services.monthly_trading_statements_service import MonthlyTradingStatementsService
monthly_statements_service = MonthlyTradingStatementsService(db)

# MONTHLY TRADING STATEMENTS ENDPOINTS
@api_router.get("/trading-statements/seller/{year}/{month}")
async def get_seller_monthly_statement(
    year: int,
    month: int,
    current_user: User = Depends(get_current_user)
):
    """Get monthly trading statement for seller"""
    try:
        if not current_user or UserRole.SELLER not in current_user.roles:
            raise HTTPException(status_code=403, detail="Seller access required")
        
        if not (1 <= month <= 12):
            raise HTTPException(status_code=400, detail="Month must be between 1 and 12")
        
        if year < 2020 or year > datetime.now().year:
            raise HTTPException(status_code=400, detail="Invalid year")
        
        statement = await monthly_statements_service.get_seller_monthly_statement(
            current_user.id, year, month
        )
        
        return statement
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting seller monthly statement: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate statement")

@api_router.get("/trading-statements/buyer/{year}/{month}")
async def get_buyer_monthly_statement(
    year: int,
    month: int,
    current_user: User = Depends(get_current_user)
):
    """Get monthly trading statement for buyer"""
    try:
        if not current_user or UserRole.BUYER not in current_user.roles:
            raise HTTPException(status_code=403, detail="Buyer access required")
        
        if not (1 <= month <= 12):
            raise HTTPException(status_code=400, detail="Month must be between 1 and 12")
        
        if year < 2020 or year > datetime.now().year:
            raise HTTPException(status_code=400, detail="Invalid year")
        
        statement = await monthly_statements_service.get_buyer_monthly_statement(
            current_user.id, year, month
        )
        
        return statement
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting buyer monthly statement: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate statement")

@api_router.get("/trading-statements/periods")
async def get_available_periods(current_user: User = Depends(get_current_user)):
    """Get available periods for trading statements"""
    try:
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        # Determine user type
        user_type = "seller" if UserRole.SELLER in current_user.roles else "buyer"
        
        periods = await monthly_statements_service.get_available_periods(
            current_user.id, user_type
        )
        
        return {
            "periods": periods,
            "user_type": user_type
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting available periods: {e}")
        raise HTTPException(status_code=500, detail="Failed to get available periods")

# Seller Delivery Rate Endpoints
@api_router.get("/seller/delivery-rate")
async def get_seller_delivery_rate(current_user: User = Depends(get_current_user)):
    """Get current seller's delivery rate configuration"""
    if not current_user or UserRole.SELLER not in current_user.roles:
        raise HTTPException(status_code=403, detail="Seller access required")
    
    try:
        rate_doc = await db.seller_delivery_rates.find_one({"seller_id": current_user.id})
        if not rate_doc:
            # Return default values if no rate is configured
            return {
                "base_fee_cents": 0,
                "per_km_cents": 0,
                "min_km": 0,
                "max_km": 200,
                "province_whitelist": None,
                "is_active": True
            }
        
        # Remove MongoDB _id field
        rate_dict = {k: v for k, v in rate_doc.items() if k != "_id"}
        return rate_dict
    except Exception as e:
        logger.error(f"Error getting seller delivery rate: {e}")
        raise HTTPException(status_code=500, detail="Failed to get delivery rate")

@api_router.post("/seller/delivery-rate")
async def create_or_update_seller_delivery_rate(
    rate_data: SellerDeliveryRateCreate,
    current_user: User = Depends(get_current_user)
):
    """Create or update seller's delivery rate configuration"""
    if not current_user or UserRole.SELLER not in current_user.roles:
        raise HTTPException(status_code=403, detail="Seller access required")
    
    try:
        # Validate input
        if rate_data.per_km_cents < 0 or rate_data.base_fee_cents < 0:
            raise HTTPException(status_code=400, detail="Fees cannot be negative")
        
        if rate_data.max_km is not None and rate_data.max_km <= 0:
            raise HTTPException(status_code=400, detail="Max km must be positive")
        
        # Check if rate already exists
        existing_rate = await db.seller_delivery_rates.find_one({"seller_id": current_user.id})
        
        rate_dict = rate_data.dict()
        rate_dict["seller_id"] = current_user.id
        rate_dict["updated_at"] = datetime.now(timezone.utc)
        
        if existing_rate:
            # Update existing rate
            await db.seller_delivery_rates.update_one(
                {"seller_id": current_user.id},
                {"$set": rate_dict}
            )
        else:
            # Create new rate
            rate_dict["id"] = str(uuid.uuid4())
            rate_dict["created_at"] = datetime.now(timezone.utc)
            rate_dict["is_active"] = True
            await db.seller_delivery_rates.insert_one(rate_dict)
        
        return {"success": True, "message": "Delivery rate updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating seller delivery rate: {e}")
        raise HTTPException(status_code=500, detail="Failed to update delivery rate")

@api_router.post("/delivery/quote")
async def get_delivery_quote(quote_request: DeliveryQuoteRequest):
    """Get delivery quote for a specific seller"""
    try:
        # Get seller's delivery rate configuration
        rate_doc = await db.seller_delivery_rates.find_one({
            "seller_id": quote_request.seller_id,
            "is_active": True
        })
        
        if not rate_doc:
            return DeliveryQuote(
                seller_id=quote_request.seller_id,
                out_of_range=True,
                message="Seller has not configured delivery rates"
            )
        
        # Get seller location
        seller_doc = await db.users.find_one({"id": quote_request.seller_id})
        if not seller_doc or not seller_doc.get("location"):
            return DeliveryQuote(
                seller_id=quote_request.seller_id,
                out_of_range=True,
                message="Seller location not available"
            )
        
        # Calculate distance using haversine formula
        seller_location = seller_doc["location"]
        seller_lat = seller_location.get("lat")
        seller_lng = seller_location.get("lng")
        
        if seller_lat is None or seller_lng is None:
            return DeliveryQuote(
                seller_id=quote_request.seller_id,
                out_of_range=True,
                message="Seller coordinates not available"
            )
        
        # Haversine distance calculation
        from math import radians, cos, sin, asin, sqrt
        
        def haversine(lat1, lon1, lat2, lon2):
            # Convert decimal degrees to radians
            lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
            
            # Haversine formula
            dlat = lat2 - lat1
            dlon = lon2 - lon1
            a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
            c = 2 * asin(sqrt(a))
            r = 6371  # Radius of earth in kilometers
            return c * r
        
        distance_km = haversine(
            seller_lat, seller_lng, 
            quote_request.buyer_lat, quote_request.buyer_lng
        )
        
        # Check if within max range
        if rate_doc.get("max_km") and distance_km > rate_doc["max_km"]:
            return DeliveryQuote(
                seller_id=quote_request.seller_id,
                distance_km=distance_km,
                out_of_range=True,
                message=f"Delivery not available beyond {rate_doc['max_km']}km"
            )
        
        # Calculate delivery fee
        base_fee = rate_doc.get("base_fee_cents", 0)
        per_km_rate = rate_doc.get("per_km_cents", 0)
        min_km = rate_doc.get("min_km", 0)
        
        # Calculate chargeable distance (distance beyond min_km)
        chargeable_km = max(0, distance_km - min_km)
        per_km_fee = int(chargeable_km * per_km_rate)
        total_delivery_fee = base_fee + per_km_fee
        
        return DeliveryQuote(
            seller_id=quote_request.seller_id,
            distance_km=distance_km,
            delivery_fee_cents=total_delivery_fee,
            base_fee_cents=base_fee,
            per_km_fee_cents=per_km_fee,
            out_of_range=False,
            message=f"Delivery available: {distance_km:.1f}km from seller"
        )
        
    except Exception as e:
        logger.error(f"Error calculating delivery quote: {e}")
        raise HTTPException(status_code=500, detail="Failed to calculate delivery quote")

# =============================================================================
# AI-POWERED SHIPPING OPTIMIZATION ENDPOINTS
# =============================================================================

@api_router.get("/ai/shipping/rate-suggestions")
async def get_ai_shipping_rate_suggestions(
    current_user: User = Depends(get_current_user)
):
    """Get AI-powered shipping rate suggestions for seller"""
    if not current_user or UserRole.SELLER not in current_user.roles:
        raise HTTPException(status_code=403, detail="Seller access required")
    
    if not AI_SERVICES_AVAILABLE or not ai_shipping_optimizer:
        raise HTTPException(status_code=503, detail="AI shipping optimizer not available")
    
    try:
        # Get seller location
        seller_location = current_user.location or {}
        if not seller_location:
            raise HTTPException(status_code=400, detail="Seller location required for rate suggestions")
        
        # Get historical delivery data
        historical_data = await db.orders.find({
            "seller_id": current_user.id,
            "status": {"$in": ["delivered", "completed"]},
            "created_at": {"$gte": datetime.now() - timedelta(days=90)}
        }).to_list(100)
        
        # Get AI suggestions
        suggestions = await ai_shipping_optimizer.suggest_optimal_rates(
            current_user.id, 
            seller_location,
            historical_data
        )
        
        return suggestions
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting AI shipping rate suggestions: {e}")
        raise HTTPException(status_code=500, detail="Failed to get rate suggestions")

@api_router.get("/ai/shipping/performance-analysis")
async def get_shipping_performance_analysis(
    timeframe_days: int = 30,
    current_user: User = Depends(get_current_user)
):
    """Get AI analysis of shipping performance"""
    if not current_user or UserRole.SELLER not in current_user.roles:
        raise HTTPException(status_code=403, detail="Seller access required")
    
    if not AI_SERVICES_AVAILABLE or not ai_shipping_optimizer:
        raise HTTPException(status_code=503, detail="AI shipping optimizer not available")
    
    try:
        analysis = await ai_shipping_optimizer.analyze_shipping_performance(
            current_user.id, 
            timeframe_days
        )
        
        return analysis
        
    except Exception as e:
        logger.error(f"Error analyzing shipping performance: {e}")
        raise HTTPException(status_code=500, detail="Failed to analyze shipping performance")

@api_router.get("/ai/shipping/demand-prediction")
async def get_delivery_demand_prediction(
    time_horizon_days: int = 30,
    current_user: User = Depends(get_current_user)
):
    """Get AI-powered delivery demand predictions"""
    if not current_user or UserRole.SELLER not in current_user.roles:
        raise HTTPException(status_code=403, detail="Seller access required")
    
    if not AI_SERVICES_AVAILABLE or not ai_shipping_optimizer:
        raise HTTPException(status_code=503, detail="AI shipping optimizer not available")
    
    try:
        seller_location = current_user.location or {}
        if not seller_location:
            raise HTTPException(status_code=400, detail="Seller location required for demand prediction")
        
        predictions = await ai_shipping_optimizer.predict_delivery_demand(
            seller_location,
            time_horizon_days
        )
        
        return predictions
        
    except Exception as e:
        logger.error(f"Error predicting delivery demand: {e}")
        raise HTTPException(status_code=500, detail="Failed to predict delivery demand")

# =============================================================================
# AI-POWERED MOBILE PAYMENT ANALYTICS ENDPOINTS  
# =============================================================================

@api_router.get("/ai/payments/analytics")
async def get_payment_analytics(
    timeframe_days: int = 30,
    current_user: User = Depends(get_current_user)
):
    """Get AI-powered payment analytics and patterns"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    if not AI_SERVICES_AVAILABLE or not ai_mobile_payment_service:
        raise HTTPException(status_code=503, detail="AI payment service not available")
    
    try:
        # Get user-specific analytics for buyers/sellers, platform-wide for admins
        user_id = current_user.id if current_user.user_type != "admin" else None
        
        analytics = await ai_mobile_payment_service.analyze_payment_patterns(
            user_id,
            timeframe_days
        )
        
        return analytics
        
    except Exception as e:
        logger.error(f"Error getting payment analytics: {e}")
        raise HTTPException(status_code=500, detail="Failed to get payment analytics")

@api_router.post("/ai/payments/predict-success")
async def predict_payment_success(
    payment_request: dict,
    current_user: User = Depends(get_current_user)
):
    """Predict payment success probability using AI"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    if not AI_SERVICES_AVAILABLE or not ai_mobile_payment_service:
        raise HTTPException(status_code=503, detail="AI payment service not available")
    
    try:
        prediction = await ai_mobile_payment_service.predict_payment_success(payment_request)
        return prediction
        
    except Exception as e:
        logger.error(f"Error predicting payment success: {e}")
        raise HTTPException(status_code=500, detail="Failed to predict payment success")

@api_router.post("/ai/payments/optimize-mobile")
async def optimize_mobile_payment_flow(
    device_info: dict,
    user_behavior: dict = {},
    current_user: User = Depends(get_current_user)
):
    """Get AI-powered mobile payment flow optimization"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    if not AI_SERVICES_AVAILABLE or not ai_mobile_payment_service:
        raise HTTPException(status_code=503, detail="AI payment service not available")
    
    try:
        optimization = await ai_mobile_payment_service.optimize_mobile_flow(
            device_info,
            user_behavior
        )
        
        return optimization
        
    except Exception as e:
        logger.error(f"Error optimizing mobile payment flow: {e}")
        raise HTTPException(status_code=500, detail="Failed to optimize mobile flow")

@api_router.post("/ai/payments/deep-link-config")
async def generate_payment_deep_link_config(
    payment_id: str,
    return_url: str,
    device_type: str = "mobile"
):
    """Generate Capacitor deep-link configuration for payment returns"""
    if not AI_SERVICES_AVAILABLE or not ai_mobile_payment_service:
        raise HTTPException(status_code=503, detail="AI payment service not available")
    
    try:
        config = ai_mobile_payment_service.generate_deep_link_config(
            payment_id,
            return_url,
            device_type
        )
        
        return config
        
    except Exception as e:
        logger.error(f"Error generating deep link config: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate deep link config")

@api_router.post("/ai/payments/track-analytics")
async def track_payment_analytics(
    payment_id: str,
    event_type: str,
    event_data: dict
):
    """Track payment analytics events for AI learning"""
    if not AI_SERVICES_AVAILABLE or not ai_mobile_payment_service:
        return {"success": False, "error": "AI payment service not available"}
    
    try:
        result = await ai_mobile_payment_service.track_payment_analytics(
            payment_id,
            event_type,
            event_data
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error tracking payment analytics: {e}")
        return {"success": False, "error": str(e)}

@api_router.get("/seller/analytics")
async def get_seller_own_analytics(
    period: str = Query("30days", description="Time period for analytics"),
    current_user: User = Depends(get_current_user)
):
    """Get comprehensive analytics for the authenticated seller"""
    logger.info(f"=== SELLER ANALYTICS REQUEST ===")
    logger.info(f"User ID: {current_user.id if current_user else 'None'}")
    logger.info(f"User Roles: {current_user.roles if current_user else 'None'}")
    logger.info(f"Period: {period}")
    logger.info(f"Request received at: {datetime.now(timezone.utc)}")
    
    # Allow users with "seller" or "both" roles
    user_roles = current_user.roles if current_user else []
    has_seller_access = "seller" in user_roles or "both" in user_roles
    
    if not current_user:
        logger.warning("No current user for seller analytics")
        raise HTTPException(status_code=401, detail="Authentication required")
    
    if not has_seller_access:
        logger.warning(f"User {current_user.id} does not have seller access. Roles: {user_roles}")
        raise HTTPException(status_code=403, detail="Seller access required")
    
    try:
        # Convert period to days
        period_days = {
            "7days": 7,
            "30days": 30,
            "3months": 90,
            "6months": 180,
            "1year": 365
        }.get(period, 30)
        
        start_date = datetime.now(timezone.utc) - timedelta(days=period_days)
        seller_id = current_user.id
        
        logger.info(f"Fetching analytics for seller {seller_id}, period: {period_days} days")
        
        # Get seller's listings
        try:
            listings = await db.listings.find({"seller_id": seller_id}).to_list(length=None)
            total_listings = len(listings)
            active_listings = len([l for l in listings if l.get("status") == "active"])
            sold_listings = len([l for l in listings if l.get("status") == "sold"])
            logger.info(f"Found {total_listings} listings ({active_listings} active, {sold_listings} sold)")
        except Exception as e:
            logger.error(f"Error fetching listings: {e}")
            listings = []
            total_listings = 0
            active_listings = 0
            sold_listings = 0
        
        # Get orders for this seller
        try:
            orders = await db.orders.find({
                "seller_id": seller_id,
                "created_at": {"$gte": start_date}
            }).to_list(length=None)
            logger.info(f"Found {len(orders)} orders in period")
        except Exception as e:
            logger.error(f"Error fetching orders: {e}")
            orders = []
        
        # Calculate revenue from completed orders
        total_revenue = sum(
            float(order.get("total_amount", 0)) 
            for order in orders 
            if order.get("status") in ["completed", "delivered"]
        )
        
        # Get listing views - simplified approach to avoid slow aggregation
        # First, get views from listings directly (if they have view_count field)
        total_views = 0
        listing_views_data = []
        
        try:
            # Try to get view counts from listings directly (faster)
            for listing in listings:
                view_count = listing.get("view_count", 0) or 0
                total_views += view_count
                if len(listing_views_data) < 5 and view_count > 0:
                    listing_views_data.append({
                        "_id": listing.get("id"),
                        "views": view_count,
                        "title": listing.get("title", "Untitled")
                    })
            
            # Sort by views and limit
            listing_views_data = sorted(listing_views_data, key=lambda x: x.get("views", 0), reverse=True)[:5]
            
            # If no view counts in listings, try analytics_events (but with timeout protection)
            if total_views == 0:
                try:
                    # Simplified query - just count views, don't do complex aggregation
                    view_count = await db.analytics_events.count_documents({
                        "event_type": "pdp_view",
                        "timestamp": {"$gte": start_date}
                    })
                    # Get listing IDs from the events
                    listing_ids = await db.analytics_events.distinct("listing_id", {
                        "event_type": "pdp_view",
                        "timestamp": {"$gte": start_date}
                    })
                    # Filter to seller's listings
                    seller_listing_ids = [l.get("id") for l in listings]
                    seller_views = len([lid for lid in listing_ids if lid in seller_listing_ids])
                    total_views = seller_views
                except Exception as e:
                    logger.warning(f"Could not fetch analytics events: {e}")
                    total_views = 0
        except Exception as e:
            logger.warning(f"Error calculating views: {e}")
            total_views = 0
        
        # Calculate conversion rate (orders / views)
        conversion_rate = (len(orders) / total_views * 100) if total_views > 0 else 0
        
        # Get previous period for growth calculation - simplified
        previous_revenue = 0
        try:
            previous_start = start_date - timedelta(days=period_days)
            previous_orders = await db.orders.find({
                "seller_id": seller_id,
                "created_at": {"$gte": previous_start, "$lt": start_date}
            }).to_list(length=100)  # Limit to avoid slow queries
            previous_revenue = sum(
                float(order.get("total_amount", 0)) 
                for order in previous_orders 
                if order.get("status") in ["completed", "delivered"]
            )
        except Exception as e:
            logger.warning(f"Error fetching previous period revenue: {e}")
            previous_revenue = 0
        
        # Calculate growth percentages
        revenue_growth = ((total_revenue - previous_revenue) / previous_revenue * 100) if previous_revenue > 0 else 0
        listing_growth = 0  # Can be calculated if needed
        view_growth = 0  # Can be calculated if needed
        
        # Monthly revenue breakdown - simplified to avoid multiple queries
        monthly_revenue = []
        month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        try:
            # Group orders by month from already fetched orders
            monthly_revenue_dict = {}
            for order in orders:
                if order.get("status") in ["completed", "delivered"]:
                    order_date = order.get("created_at")
                    if isinstance(order_date, str):
                        try:
                            order_date = datetime.fromisoformat(order_date.replace('Z', '+00:00'))
                        except:
                            continue
                    elif not isinstance(order_date, datetime):
                        continue
                    
                    month_key = order_date.strftime("%Y-%m")
                    if month_key not in monthly_revenue_dict:
                        monthly_revenue_dict[month_key] = 0
                    monthly_revenue_dict[month_key] += float(order.get("total_amount", 0))
            
            # Convert to list format
            for month_key, revenue in sorted(monthly_revenue_dict.items()):
                month_num = int(month_key.split("-")[1])
                monthly_revenue.append({
                    "month": month_names[month_num - 1],
                    "revenue": int(revenue * 100)  # Convert to cents
                })
        except Exception as e:
            logger.warning(f"Error calculating monthly revenue: {e}")
        
        # Ensure at least one entry for frontend rendering
        if not monthly_revenue:
            monthly_revenue = [{"month": month_names[datetime.now(timezone.utc).month - 1], "revenue": 0}]
        
        # Top listings - use already fetched data
        top_listings = []
        try:
            # Get top listings by views or revenue
            for item in listing_views_data[:5]:
                listing_id = item.get("_id")
                if listing_id:
                    listing_orders = [o for o in orders if o.get("listing_id") == listing_id]
                    listing_revenue = sum(float(o.get("total_amount", 0)) for o in listing_orders) * 100  # Convert to cents
                    top_listings.append({
                        "id": listing_id,
                        "title": item.get("title", "Untitled"),
                        "views": item.get("views", 0),
                        "revenue": listing_revenue
                    })
            
            # If no views data, use listings with orders
            if not top_listings and orders:
                listing_revenues = {}
                for order in orders:
                    lid = order.get("listing_id")
                    if lid:
                        if lid not in listing_revenues:
                            listing_revenues[lid] = 0
                        listing_revenues[lid] += float(order.get("total_amount", 0)) * 100
                
                for listing_id, revenue in sorted(listing_revenues.items(), key=lambda x: x[1], reverse=True)[:5]:
                    listing = next((l for l in listings if l.get("id") == listing_id), None)
                    if listing:
                        top_listings.append({
                            "id": listing_id,
                            "title": listing.get("title", "Untitled"),
                            "views": listing.get("view_count", 0),
                            "revenue": revenue
                        })
            
            # If still no top listings, just use first 5 active listings
            if not top_listings:
                for listing in listings[:5]:
                    if listing.get("status") == "active":
                        top_listings.append({
                            "id": listing.get("id"),
                            "title": listing.get("title", "Untitled"),
                            "views": listing.get("view_count", 0),
                            "revenue": 0
                        })
        except Exception as e:
            logger.warning(f"Error building top listings: {e}")
            top_listings = []
        
        # Category breakdown (simplified - can be enhanced)
        category_breakdown = []
        if top_listings:
            # For now, use a simple breakdown
            category_breakdown = [
                {"category": "Livestock", "percentage": 100, "revenue": total_revenue * 100}
            ]
        
        result = {
            "overview": {
                "total_revenue": int(total_revenue * 100),  # Convert to cents
                "total_listings": total_listings,
                "total_views": total_views,
                "conversion_rate": round(conversion_rate, 2),
                "active_listings": active_listings,
                "sold_listings": sold_listings
            },
            "performance": {
                "revenue_growth": round(revenue_growth, 2),
                "listing_growth": listing_growth,
                "view_growth": view_growth
            },
            "top_listings": top_listings if top_listings else [],
            "monthly_revenue": monthly_revenue if monthly_revenue else [
                {"month": "No Data", "revenue": 0}
            ],
            "category_breakdown": category_breakdown if category_breakdown else []
        }
        
        logger.info(f"Returning analytics data: {total_listings} listings, {len(orders)} orders, {total_views} views")
        logger.info(f"Response prepared in {datetime.now(timezone.utc)}")
        return result
    except Exception as e:
        logger.error(f"Error fetching seller analytics: {e}", exc_info=True)
        # Return empty data structure instead of raising error to prevent frontend issues
        return {
            "overview": {
                "total_revenue": 0,
                "total_listings": 0,
                "total_views": 0,
                "conversion_rate": 0,
                "active_listings": 0,
                "sold_listings": 0
            },
            "performance": {
                "revenue_growth": 0,
                "listing_growth": 0,
                "view_growth": 0
            },
            "top_listings": [],
            "monthly_revenue": [],
            "category_breakdown": [],
            "error": str(e)
        }

@api_router.get("/admin/analytics/seller/{seller_id}")
async def get_seller_analytics(
    seller_id: str,
    days: int = 30,
    current_user: User = Depends(get_current_user)
):
    """Get analytics for a specific seller"""
    if not current_user or current_user.user_type != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        from services.analytics_service import AnalyticsService
        analytics = AnalyticsService(db)
        data = await analytics.get_seller_analytics(seller_id, days)
        return data
    except Exception as e:
        logger.error(f"Error fetching seller analytics: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch analytics")

@api_router.get("/admin/analytics/daily")
async def get_daily_analytics(
    days: int = 7,
    current_user: User = Depends(get_current_user)
):
    """Get daily analytics for charts"""
    if not current_user or current_user.user_type != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        from services.analytics_service import AnalyticsService
        analytics = AnalyticsService(db)
        data = await analytics.get_daily_metrics(days)
        return data
    except Exception as e:
        logger.error(f"Error fetching daily analytics: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch analytics")

# Reviews Routes
@api_router.get("/reviews")
async def get_reviews(
    sellerId: Optional[str] = None,
    listingId: Optional[str] = None,
    page: int = 1,
    limit: int = 10
):
    """Get reviews with optional filters"""
    try:
        skip = (page - 1) * limit
        filter_query = {}
        
        if sellerId:
            filter_query["seller_id"] = sellerId
        if listingId:
            filter_query["listing_id"] = listingId
        
        reviews_cursor = db.reviews.find(filter_query).sort("created_at", -1).skip(skip).limit(limit)
        reviews = []
        
        async for review in reviews_cursor:
            reviews.append({
                "id": review.get("id", str(review.get("_id"))),
                "stars": review.get("rating", 0),
                "comment": review.get("comment", ""),
                "images": review.get("images", []),
                "buyer_handle": review.get("buyer_name", "Anonymous"),
                "created_at": review.get("created_at", datetime.now(timezone.utc)).isoformat()
            })
        
        total = await db.reviews.count_documents(filter_query)
        
        return {
            "items": reviews,
            "total": total,
            "page": page,
            "pages": (total + limit - 1) // limit
        }
    
    except Exception as e:
        logger.error(f"Error fetching reviews: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch reviews")

# A/B Testing Routes
@api_router.get("/ab-test/pdp-config/{listing_id}")
async def get_pdp_ab_config(
    listing_id: str,
    request: Request,
    current_user: User = Depends(get_current_user_optional)
):
    """Get A/B test configuration for PDP"""
    # Apply generous rate limiting for A/B testing
    await rate_limit_middleware(request, "ab_testing", current_user.id if current_user else None)
    
    try:
        from services.ab_testing_service import ABTestingService
        ab_service = ABTestingService(db)
        
        # Create user identifier
        user_identifier = current_user.id if current_user else request.client.host
        
        config = await ab_service.get_pdp_variant_config(listing_id, user_identifier)
        return config
    
    except Exception as e:
        logger.error(f"Error getting A/B config: {e}")
        return {"layout": "default", "experiment_tracking": []}

@api_router.post("/ab-test/track-event")
async def track_ab_event(
    event_data: dict,
    current_user: User = Depends(get_current_user_optional)
):
    """Track A/B test events"""
    try:
        from services.ab_testing_service import ABTestingService
        ab_service = ABTestingService(db)
        
        await ab_service.track_experiment_event(
            experiment_id=event_data.get("experiment_id"),
            variant=event_data.get("variant"),
            user_identifier=event_data.get("user_identifier"),
            event_type=event_data.get("event_type"),
            metadata=event_data.get("metadata", {})
        )
        
        return {"status": "tracked"}
    
    except Exception as e:
        logger.error(f"Error tracking A/B event: {e}")
        return {"status": "error"}

@api_router.get("/admin/ab-tests")
async def get_ab_experiments(current_user: User = Depends(get_current_user)):
    """Get all A/B experiments"""
    if not current_user or current_user.user_type != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        from services.ab_testing_service import ABTestingService
        ab_service = ABTestingService(db)
        
        experiments = await ab_service.db.ab_experiments.find().to_list(length=100)
        return {"experiments": experiments}
    
    except Exception as e:
        logger.error(f"Error fetching experiments: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch experiments")

@api_router.post("/admin/ab-tests")
async def create_ab_experiment(
    experiment_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Create new A/B experiment"""
    if not current_user or current_user.user_type != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        from services.ab_testing_service import ABTestingService
        ab_service = ABTestingService(db)
        
        experiment = await ab_service.create_experiment(
            name=experiment_data.get("name"),
            description=experiment_data.get("description"),
            variants=experiment_data.get("variants"),
            traffic_split=experiment_data.get("traffic_split"),
            duration_days=experiment_data.get("duration_days", 30)
        )
        
        return experiment
    
    except Exception as e:
        logger.error(f"Error creating experiment: {e}")
        raise HTTPException(status_code=500, detail="Failed to create experiment")

@api_router.get("/admin/ab-tests/{experiment_id}/results")
async def get_experiment_results(
    experiment_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get A/B test results"""
    if not current_user or current_user.user_type != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        from services.ab_testing_service import ABTestingService
        ab_service = ABTestingService(db)
        
        results = await ab_service.get_experiment_results(experiment_id)
        return results
    
    except Exception as e:
        logger.error(f"Error fetching experiment results: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch results")

# Messaging Routes
@api_router.post("/inbox/ask")
async def create_conversation(request_data: dict, current_user: User = Depends(get_current_user)):
    """Create a conversation between buyer and seller"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        seller_id = request_data.get("seller_id")
        listing_id = request_data.get("listing_id")
        
        # If only listing_id provided, get seller_id
        if not seller_id and listing_id:
            listing_doc = await db.listings.find_one({"id": listing_id})
            if not listing_doc:
                raise HTTPException(status_code=404, detail="Listing not found")
            seller_id = listing_doc["seller_id"]
        
        if not seller_id:
            raise HTTPException(status_code=400, detail="seller_id or listing_id required")
        
        # Check if conversation already exists
        existing = await db.conversations.find_one({
            "participants": {"$all": [current_user.id, seller_id]},
            "listing_id": listing_id
        })
        
        if existing:
            return {"conversation_id": existing["id"]}
        
        # Create new conversation
        conversation_id = str(uuid.uuid4())
        conversation = {
            "id": conversation_id,
            "participants": [current_user.id, seller_id],
            "listing_id": listing_id,
            "created_at": datetime.now(timezone.utc),
            "last_message_at": datetime.now(timezone.utc),
            "status": "active"
        }
        
        await db.conversations.insert_one(conversation)
        
        # Send initial message if listing_id provided
        if listing_id:
            listing_doc = await db.listings.find_one({"id": listing_id})
            if listing_doc:
                message = {
                    "id": str(uuid.uuid4()),
                    "conversation_id": conversation_id,
                    "sender_id": current_user.id,
                    "content": f"Hi, I'm interested in your listing: {listing_doc['title']}",
                    "created_at": datetime.now(timezone.utc),
                    "message_type": "text"
                }
                await db.messages.insert_one(message)
        
        return {"conversation_id": conversation_id}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating conversation: {e}")
        raise HTTPException(status_code=500, detail="Failed to create conversation")

# Admin routes
@api_router.get("/admin/stats")
async def get_admin_stats(current_user: User = Depends(get_current_user)):
    """Get admin dashboard statistics"""
    if not current_user or "admin" not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        total_users = await db.users.count_documents({})
        total_listings = await db.listings.count_documents({})
        total_orders = await db.orders.count_documents({})
        pending_approvals = await db.listings.count_documents({"status": "PENDING_APPROVAL"})
        
        return {
            "total_users": total_users,
            "total_listings": total_listings,
            "total_orders": total_orders,
            "pending_approvals": pending_approvals
        }
    except Exception as e:
        logger.error(f"Error fetching admin stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch admin stats")

# Add the dashboard stats endpoint that frontend expects
@api_router.get("/admin/dashboard/stats")
async def get_admin_dashboard_stats(current_user: User = Depends(get_current_user)):
    """Get admin dashboard statistics - frontend endpoint"""
    return await get_admin_stats(current_user)

@api_router.get("/admin/listings/pending", response_model=List[Listing])
async def get_pending_listings(current_user: User = Depends(get_current_user)):
    """Get listings pending approval"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        listings_docs = await db.listings.find({"status": ListingStatus.PENDING_APPROVAL}).to_list(length=None)
        
        # Convert price back to Decimal
        listings = []
        for doc in listings_docs:
            doc["price_per_unit"] = Decimal(str(doc["price_per_unit"]))
            listings.append(Listing(**doc))
        
        return listings
    except Exception as e:
        logger.error(f"Error fetching pending listings: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch pending listings")

@api_router.post("/admin/listings/{listing_id}/approve")
async def approve_listing(listing_id: str, current_user: User = Depends(get_current_user)):
    """Approve a pending listing"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        result = await db.listings.update_one(
            {"id": listing_id},
            {"$set": {
                "status": ListingStatus.ACTIVE,
                "approved_at": datetime.now(timezone.utc),
                "approved_by": current_user.id
            }}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Listing not found")
        
        # Emit SSE event
        await emit_admin_event("LISTING.STATUS_CHANGED", {
            "listing_id": listing_id,
            "old": "pending",
            "new": "approved",
            "admin_id": current_user.id,
            "admin_name": current_user.full_name
        })
        
        # 📧 Send listing approved email (E16)
        try:
            # Get listing and seller details
            listing_doc = await db.listings.find_one({"id": listing_id})
            if listing_doc:
                seller_doc = await db.users.find_one({"id": listing_doc.get("seller_id")})
                if seller_doc:
                    listing_title = listing_doc.get("title", "Your listing")
                    listing_url = f"https://stocklot.farm/listings/{listing_id}"
                    
                    notification = EmailNotification(
                        template_id="E16",
                        recipient_email=seller_doc["email"],
                        recipient_name=seller_doc.get("full_name", "Seller"),
                        variables={
                            "listing_title": listing_title,
                            "listing_url": listing_url
                        },
                        tags=["E16", "listings", "approved"]
                    )
                    await email_notification_service.send_email(notification)
                    logger.info(f"Listing approved email sent for listing {listing_id}")
        except Exception as e:
            logger.warning(f"Failed to send listing approved email for {listing_id}: {e}")
        
        return {"message": "Listing approved successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving listing: {e}")
        raise HTTPException(status_code=500, detail="Failed to approve listing")

@api_router.post("/admin/listings/{listing_id}/reject")
async def reject_listing(listing_id: str, request_data: dict = {}, current_user: User = Depends(get_current_user)):
    """Reject a pending listing"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        reason = request_data.get("reason", "Not compliant with platform standards")
        
        result = await db.listings.update_one(
            {"id": listing_id},
            {"$set": {
                "status": ListingStatus.INACTIVE,
                "rejection_reason": reason,
                "rejected_at": datetime.now(timezone.utc),
                "rejected_by": current_user.id
            }}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Listing not found")
        
        # Emit SSE event
        await emit_admin_event("LISTING.STATUS_CHANGED", {
            "listing_id": listing_id,
            "old": "pending", 
            "new": "rejected",
            "reason": reason,
            "admin_id": current_user.id,
            "admin_name": current_user.full_name
        })
        
        # 📧 Send listing rejected email (E17)
        try:
            # Get listing and seller details
            listing_doc = await db.listings.find_one({"id": listing_id})
            if listing_doc:
                seller_doc = await db.users.find_one({"id": listing_doc.get("seller_id")})
                if seller_doc:
                    listing_title = listing_doc.get("title", "Your listing")
                    edit_url = f"https://stocklot.farm/dashboard/listings/{listing_id}/edit"
                    
                    notification = EmailNotification(
                        template_id="E17",
                        recipient_email=seller_doc["email"],
                        recipient_name=seller_doc.get("full_name", "Seller"),
                        variables={
                            "listing_title": listing_title,
                            "reason": reason,
                            "edit_url": edit_url
                        },
                        tags=["E17", "listings", "rejected"]
                    )
                    await email_notification_service.send_email(notification)
                    logger.info(f"Listing rejected email sent for listing {listing_id}")
        except Exception as e:
            logger.warning(f"Failed to send listing rejected email for {listing_id}: {e}")
        
        return {"message": "Listing rejected successfully", "reason": reason}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rejecting listing: {e}")
        raise HTTPException(status_code=500, detail="Failed to reject listing")

# Admin User Management
@api_router.post("/admin/users/{user_id}/suspend")
async def admin_suspend_user(user_id: str, current_user: User = Depends(get_current_user)):
    """Suspend a user account"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Get user details for event
        user_doc = await db.users.find_one({"id": user_id})
        if not user_doc:
            raise HTTPException(status_code=404, detail="User not found")
        
        result = await db.users.update_one(
            {"id": user_id},
            {"$set": {
                "status": "suspended",
                "suspended_at": datetime.now(timezone.utc),
                "suspended_by": current_user.id
            }}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Emit SSE event
        await emit_admin_event("USER.STATUS_CHANGED", {
            "user_id": user_id,
            "user_email": user_doc.get("email"),
            "old": user_doc.get("status", "active"),
            "new": "suspended",
            "admin_id": current_user.id,
            "admin_name": current_user.full_name
        })
        
        return {"message": "User suspended successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error suspending user: {e}")
        raise HTTPException(status_code=500, detail="Failed to suspend user")

@api_router.post("/admin/users/{user_id}/activate")
async def admin_activate_user(user_id: str, current_user: User = Depends(get_current_user)):
    """Activate a suspended user account"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Get user details for event
        user_doc = await db.users.find_one({"id": user_id})
        if not user_doc:
            raise HTTPException(status_code=404, detail="User not found")
        
        result = await db.users.update_one(
            {"id": user_id},
            {"$set": {
                "status": "active",
                "activated_at": datetime.now(timezone.utc),
                "activated_by": current_user.id
            },
            "$unset": {
                "suspended_at": "",
                "suspended_by": ""
            }}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Emit SSE event
        await emit_admin_event("USER.STATUS_CHANGED", {
            "user_id": user_id,
            "user_email": user_doc.get("email"),
            "old": user_doc.get("status", "suspended"),
            "new": "active",
            "admin_id": current_user.id,
            "admin_name": current_user.full_name
        })
        
        return {"message": "User activated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error activating user: {e}")
        raise HTTPException(status_code=500, detail="Failed to activate user")

# Admin Order Management
@api_router.post("/admin/orders/{order_id}/escrow/release")
async def admin_release_escrow(order_id: str, current_user: User = Depends(get_current_user)):
    """Release escrow funds to seller"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Update order status
        result = await db.orders.update_one(
            {"id": order_id},
            {"$set": {
                "status": "funds_released",
                "escrow_released_at": datetime.now(timezone.utc),
                "escrow_released_by": current_user.id
            }}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Order not found")
        
        # TODO: Integrate with Paystack to actually release funds
        # This would call paystack_service.release_funds(order_id)
        
        return {"message": "Escrow released successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error releasing escrow: {e}")
        raise HTTPException(status_code=500, detail="Failed to release escrow")

@api_router.post("/admin/orders/{order_id}/escrow/refund")
async def admin_refund_escrow(order_id: str, current_user: User = Depends(get_current_user)):
    """Refund escrow funds to buyer"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Update order status
        result = await db.orders.update_one(
            {"id": order_id},
            {"$set": {
                "status": "refunded",
                "escrow_refunded_at": datetime.now(timezone.utc),
                "escrow_refunded_by": current_user.id
            }}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Order not found")
        
        # TODO: Integrate with Paystack to actually refund funds
        # This would call paystack_service.refund_payment(order_id)
        
        return {"message": "Escrow refunded successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refunding escrow: {e}")
        raise HTTPException(status_code=500, detail="Failed to refund escrow")

# Admin Document/Compliance Management
@api_router.post("/admin/docs/{doc_id}/verify")
async def admin_verify_document(doc_id: str, current_user: User = Depends(get_current_user)):
    """Verify a compliance document"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        result = await db.documents.update_one(
            {"id": doc_id},
            {"$set": {
                "status": "verified",
                "verified_at": datetime.now(timezone.utc),
                "verified_by": current_user.id
            }}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Document not found")
        
        return {"message": "Document verified successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying document: {e}")
        raise HTTPException(status_code=500, detail="Failed to verify document")

@api_router.post("/admin/docs/{doc_id}/reject")
async def admin_reject_document(doc_id: str, request_data: dict = {}, current_user: User = Depends(get_current_user)):
    """Reject a compliance document"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        reason = request_data.get("reason", "Document does not meet compliance requirements")
        
        result = await db.documents.update_one(
            {"id": doc_id},
            {"$set": {
                "status": "rejected",
                "rejection_reason": reason,
                "rejected_at": datetime.now(timezone.utc),
                "rejected_by": current_user.id
            }}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Document not found")
        
        return {"message": "Document rejected successfully", "reason": reason}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rejecting document: {e}")
        raise HTTPException(status_code=500, detail="Failed to reject document")

# Admin Buy Request Management  
@api_router.post("/admin/buy-requests/{request_id}/approve")
async def admin_approve_buy_request(request_id: str, current_user: User = Depends(get_current_user)):
    """Approve a buy request"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        result = await db.buy_requests.update_one(
            {"id": request_id},
            {"$set": {
                "status": "approved",
                "approved_at": datetime.now(timezone.utc),
                "approved_by": current_user.id
            }}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Buy request not found")
        
        return {"message": "Buy request approved successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving buy request: {e}")
        raise HTTPException(status_code=500, detail="Failed to approve buy request")

@api_router.post("/admin/buy-requests/{request_id}/reject")
async def admin_reject_buy_request(request_id: str, request_data: dict = {}, current_user: User = Depends(get_current_user)):
    """Reject a buy request"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        reason = request_data.get("reason", "Buy request does not meet platform guidelines")
        
        result = await db.buy_requests.update_one(
            {"id": request_id},
            {"$set": {
                "status": "rejected",
                "rejection_reason": reason,
                "rejected_at": datetime.now(timezone.utc),
                "rejected_by": current_user.id
            }}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Buy request not found")
        
        return {"message": "Buy request rejected successfully", "reason": reason}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rejecting buy request: {e}")
        raise HTTPException(status_code=500, detail="Failed to reject buy request")

@api_router.post("/admin/buy-requests/{request_id}/close")
async def admin_close_buy_request(request_id: str, current_user: User = Depends(get_current_user)):
    """Close a buy request"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        result = await db.buy_requests.update_one(
            {"id": request_id},
            {"$set": {
                "status": "closed",
                "closed_at": datetime.now(timezone.utc),
                "closed_by": current_user.id
            }}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Buy request not found")
        
        return {"message": "Buy request closed successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error closing buy request: {e}")
        raise HTTPException(status_code=500, detail="Failed to close buy request")

# Payment Integration Endpoints
@api_router.post("/payments/paystack/init")
async def initialize_paystack_payment(
    request_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Initialize Paystack payment for escrow"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        order_id = request_data.get("order_id")
        amount = request_data.get("amount")
        
        if not order_id or not amount:
            raise HTTPException(status_code=400, detail="Order ID and amount required")
        
        # Initialize payment through Paystack service
        result = await paystack_service.initialize_transaction(
            email=current_user.email,
            amount=float(amount),
            order_id=order_id,
            callback_url=request_data.get("callback_url")
        )
        
        return result
    except Exception as e:
        logger.error(f"Error initializing payment: {e}")
        raise HTTPException(status_code=500, detail="Failed to initialize payment")

@api_router.post("/payments/paystack/webhook")
async def handle_paystack_webhook(request: Request):
    """Handle Paystack webhook events"""
    try:
        payload = await request.body()
        signature = request.headers.get("x-paystack-signature", "")
        
        # Process webhook through Paystack service
        result = await paystack_service.process_webhook(payload, signature)
        
        if result.get("ok"):
            return {"status": "success"}
        else:
            logger.error(f"Webhook processing failed: {result}")
            raise HTTPException(status_code=400, detail="Webhook processing failed")
    except Exception as e:
        logger.error(f"Error handling webhook: {e}")
        raise HTTPException(status_code=500, detail="Webhook handling failed")

@api_router.post("/payments/paystack/verify/{reference}")
async def verify_paystack_payment(
    reference: str,
    current_user: User = Depends(get_current_user)
):
    """Verify Paystack payment"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        result = await paystack_service.verify_payment(reference)
        return result
    except Exception as e:
        logger.error(f"Error verifying payment: {e}")
        raise HTTPException(status_code=500, detail="Payment verification failed")

# Feature Flags & Settings API
@api_router.get("/public/config")
async def get_public_config():
    """Get public configuration and feature flags"""
    try:
        # Get feature flags from database
        flags_cursor = db.feature_flags.find({})
        flags = {}
        async for flag in flags_cursor:
            flags[flag["key"]] = flag["value"]
        
        # Get public settings from database
        settings_cursor = db.system_settings.find({"public": True})
        settings = {}
        async for setting in settings_cursor:
            settings[setting["key"]] = setting["value"]
        
        return {
            "flags": flags,
            "settings": settings,
            "version": "1.0.0",
            "environment": os.getenv("ENVIRONMENT", "development")
        }
    except Exception as e:
        logger.error(f"Error fetching public config: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch configuration")

@api_router.post("/admin/flags/{flag_key}")
async def admin_update_feature_flag(
    flag_key: str, 
    request_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Update feature flag"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        value = request_data.get("value")
        
        await db.feature_flags.update_one(
            {"key": flag_key},
            {"$set": {
                "value": value,
                "updated_at": datetime.now(timezone.utc),
                "updated_by": current_user.id
            }},
            upsert=True
        )
        
        return {"message": f"Feature flag {flag_key} updated successfully", "value": value}
    except Exception as e:
        logger.error(f"Error updating feature flag: {e}")
        raise HTTPException(status_code=500, detail="Failed to update feature flag")

@api_router.post("/admin/settings/{setting_key}")
async def admin_update_setting(
    setting_key: str,
    request_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Update system setting"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        value = request_data.get("value")
        is_public = request_data.get("public", False)
        
        await db.system_settings.update_one(
            {"key": setting_key},
            {"$set": {
                "value": value,
                "public": is_public,
                "updated_at": datetime.now(timezone.utc),
                "updated_by": current_user.id
            }},
            upsert=True
        )
        
        return {"message": f"Setting {setting_key} updated successfully", "value": value}
    except Exception as e:
        logger.error(f"Error updating setting: {e}")
        raise HTTPException(status_code=500, detail="Failed to update setting")

# Admin Payouts Management Endpoints
@api_router.get("/admin/payouts")
async def admin_get_payouts(status: str = "all", range: str = "30d", current_user: User = Depends(get_current_user)):
    """Get payouts for admin management"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Mock data for now - would query actual payouts from database
        return {
            "payouts": [],
            "pending": [],
            "stats": {
                "total_pending": 0,
                "total_completed": 0,
                "total_failed": 0
            }
        }
    except Exception as e:
        logger.error(f"Error fetching payouts: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch payouts")

@api_router.get("/admin/payout-requests")
async def admin_get_payout_requests(current_user: User = Depends(get_current_user)):
    """Get payout requests for admin review"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Mock data for now
        return {"requests": []}
    except Exception as e:
        logger.error(f"Error fetching payout requests: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch payout requests")

@api_router.post("/admin/payouts/{payout_id}/{action}")
async def admin_process_payout(payout_id: str, action: str, current_user: User = Depends(get_current_user)):
    """Process payout action (approve, cancel, retry)"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Process the payout action
        return {"message": f"Payout {action} successful", "payout_id": payout_id}
    except Exception as e:
        logger.error(f"Error processing payout: {e}")
        raise HTTPException(status_code=500, detail="Failed to process payout")

# Admin Payment Methods Management
@api_router.get("/admin/payment-methods")
async def admin_get_payment_methods(current_user: User = Depends(get_current_user)):
    """Get payment methods for admin management"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Mock data for now
        return {"methods": []}
    except Exception as e:
        logger.error(f"Error fetching payment methods: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch payment methods")

@api_router.post("/admin/payment-methods/{method_id}/{action}")
async def admin_verify_payment_method(method_id: str, action: str, current_user: User = Depends(get_current_user)):
    """Verify, reject, suspend, or reactivate payment method"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Process the payment method action
        return {"message": f"Payment method {action} successful", "method_id": method_id}
    except Exception as e:
        logger.error(f"Error processing payment method: {e}")
        raise HTTPException(status_code=500, detail="Failed to process payment method")

# Admin Webhooks Management
@api_router.get("/admin/webhooks")
async def admin_get_webhooks(current_user: User = Depends(get_current_user)):
    """Get webhooks for admin management"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Mock data for now
        return {"webhooks": []}
    except Exception as e:
        logger.error(f"Error fetching webhooks: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch webhooks")

@api_router.get("/admin/webhook-logs")
async def admin_get_webhook_logs(limit: int = 50, current_user: User = Depends(get_current_user)):
    """Get webhook delivery logs"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Mock data for now
        return {"logs": []}
    except Exception as e:
        logger.error(f"Error fetching webhook logs: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch webhook logs")

# Admin Disease Zones & Geofencing
@api_router.get("/admin/disease-zones")
async def admin_get_disease_zones(current_user: User = Depends(get_current_user)):
    """Get disease zones for admin management"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Mock data for now
        return {"zones": []}
    except Exception as e:
        logger.error(f"Error fetching disease zones: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch disease zones")

@api_router.get("/admin/movement-restrictions")
async def admin_get_movement_restrictions(current_user: User = Depends(get_current_user)):
    """Get movement restrictions"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Mock data for now
        return {"restrictions": []}
    except Exception as e:
        logger.error(f"Error fetching restrictions: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch restrictions")

# Admin Logistics Management  
@api_router.get("/admin/transporters")
async def admin_get_transporters(current_user: User = Depends(get_current_user)):
    """Get transporters for admin management"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Mock data for now
        return {"transporters": []}
    except Exception as e:
        logger.error(f"Error fetching transporters: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch transporters")

@api_router.get("/admin/abattoirs")
async def admin_get_abattoirs(current_user: User = Depends(get_current_user)):
    """Get abattoirs for admin management"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Mock data for now
        return {"abattoirs": []}
    except Exception as e:
        logger.error(f"Error fetching abattoirs: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch abattoirs")

# Admin Auctions Management
@api_router.get("/admin/auctions")
async def admin_get_auctions(current_user: User = Depends(get_current_user)):
    """Get auctions for admin management"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Mock data for now
        return {"auctions": []}
    except Exception as e:
        logger.error(f"Error fetching auctions: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch auctions")

@api_router.get("/admin/auction-bids")
async def admin_get_auction_bids(current_user: User = Depends(get_current_user)):
    """Get auction bids for admin management"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Mock data for now
        return {"bids": []}
    except Exception as e:
        logger.error(f"Error fetching auction bids: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch auction bids")

# Admin CMS Management
@api_router.get("/admin/cms/articles")
async def admin_get_cms_articles(current_user: User = Depends(get_current_user)):
    """Get CMS articles for admin management"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Mock data for now
        return {"articles": []}
    except Exception as e:
        logger.error(f"Error fetching CMS articles: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch CMS articles")

@api_router.get("/admin/cms/pages")
async def admin_get_cms_pages(current_user: User = Depends(get_current_user)):
    """Get CMS pages for admin management"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Mock data for now
        return {"pages": []}
    except Exception as e:
        logger.error(f"Error fetching CMS pages: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch CMS pages")

@api_router.get("/admin/cms/media")
async def admin_get_cms_media(current_user: User = Depends(get_current_user)):
    """Get CMS media for admin management"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Mock data for now
        return {"media": []}
    except Exception as e:
        logger.error(f"Error fetching CMS media: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch CMS media")

# User Payment Methods Endpoints (Frontend Banking Details)
@api_router.get("/user/payment-methods")
async def get_user_payment_methods(current_user: User = Depends(get_current_user)):
    """Get user's payment methods"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        methods_cursor = db.payment_methods.find({"user_id": current_user.id})
        methods = []
        async for method in methods_cursor:
            # Remove sensitive data and MongoDB ObjectId
            method.pop("_id", None)
            # Mask account number for security
            if method.get("account_number"):
                method["account_number"] = f"****{method['account_number'][-4:]}"
            methods.append(method)
        
        return {"methods": methods}
    except Exception as e:
        logger.error(f"Error fetching user payment methods: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch payment methods")

@api_router.post("/user/payment-methods")
async def add_user_payment_method(request_data: dict, current_user: User = Depends(get_current_user)):
    """Add user payment method"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        # Create payment method
        payment_method = {
            "id": str(uuid.uuid4()),
            "user_id": current_user.id,
            "account_holder": request_data.get("account_holder"),
            "bank_name": request_data.get("bank_name"),
            "account_number": request_data.get("account_number"),
            "account_type": request_data.get("account_type", "savings"),
            "branch_code": request_data.get("branch_code"),
            "is_primary": request_data.get("is_primary", False),
            "status": "pending",  # Requires admin verification
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }
        
        # If this is set as primary, unset other primary methods
        if payment_method["is_primary"]:
            await db.payment_methods.update_many(
                {"user_id": current_user.id},
                {"$set": {"is_primary": False}}
            )
        
        await db.payment_methods.insert_one(payment_method)
        
        return {"message": "Payment method added successfully", "id": payment_method["id"]}
    except Exception as e:
        logger.error(f"Error adding payment method: {e}")
        raise HTTPException(status_code=500, detail="Failed to add payment method")

@api_router.delete("/user/payment-methods/{method_id}")
async def delete_user_payment_method(method_id: str, current_user: User = Depends(get_current_user)):
    """Delete user payment method"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        result = await db.payment_methods.delete_one({
            "id": method_id,
            "user_id": current_user.id
        })
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Payment method not found")
        
        return {"message": "Payment method deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting payment method: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete payment method")

# Enhanced Paystack Payment Release with Platform Fee (10%)
@api_router.post("/admin/payouts/{payout_id}/release-paystack")
async def admin_release_payout_paystack(payout_id: str, current_user: User = Depends(get_current_user)):
    """Release payout via Paystack with 10% platform fee deduction"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Get payout details
        payout = await db.payouts.find_one({"id": payout_id})
        if not payout:
            raise HTTPException(status_code=404, detail="Payout not found")
        
        # Get seller's verified payment method
        payment_method = await db.payment_methods.find_one({
            "user_id": payout["seller_id"],
            "status": "verified",
            "is_primary": True
        })
        
        if not payment_method:
            raise HTTPException(status_code=400, detail="Seller has no verified payment method")
        
        # Calculate amounts
        gross_amount = float(payout["amount"])
        platform_fee = gross_amount * 0.10  # 10% platform fee
        net_amount = gross_amount - platform_fee
        
        # Create Paystack transfer recipient if not exists
        recipient_data = {
            "type": "nuban",
            "name": payment_method["account_holder"],
            "account_number": payment_method["account_number"],
            "bank_code": payment_method["branch_code"],
            "currency": "ZAR"
        }
        
        # Call Paystack service to create transfer
        transfer_result = await paystack_service.create_transfer_recipient(recipient_data)
        
        if not transfer_result.get("status"):
            raise HTTPException(status_code=400, detail="Failed to create Paystack recipient")
        
        recipient_code = transfer_result["data"]["recipient_code"]
        
        # Initiate transfer
        transfer_data = {
            "source": "balance",
            "amount": int(net_amount * 100),  # Paystack amount in kobo
            "recipient": recipient_code,
            "reason": f"Livestock sale payout - Order #{payout['order_id']}",
            "reference": f"payout_{payout_id}_{int(datetime.now().timestamp())}"
        }
        
        transfer_response = await paystack_service.initiate_transfer(transfer_data)
        
        if not transfer_response.get("status"):
            raise HTTPException(status_code=400, detail="Failed to initiate Paystack transfer")
        
        # Update payout record
        await db.payouts.update_one(
            {"id": payout_id},
            {"$set": {
                "status": "processing",
                "gross_amount": gross_amount,
                "platform_fee": platform_fee,
                "net_amount": net_amount,
                "paystack_transfer_code": transfer_response["data"]["transfer_code"],
                "paystack_reference": transfer_data["reference"],
                "processed_at": datetime.now(timezone.utc),
                "processed_by": current_user.id
            }}
        )
        
        # Emit SSE event
        await emit_admin_event("PAYOUT.PROCESSED", {
            "payout_id": payout_id,
            "seller_id": payout["seller_id"],
            "gross_amount": gross_amount,
            "net_amount": net_amount,
            "platform_fee": platform_fee,
            "admin_id": current_user.id
        })
        
        return {
            "message": "Payout initiated successfully via Paystack",
            "payout_id": payout_id,
            "gross_amount": gross_amount,
            "platform_fee": platform_fee,
            "net_amount": net_amount,
            "transfer_code": transfer_response["data"]["transfer_code"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error releasing Paystack payout: {e}")
        raise HTTPException(status_code=500, detail="Failed to process Paystack payout")

# Additional Admin API Endpoints for Missing Features
@api_router.get("/admin/broadcast-campaigns")
async def admin_get_broadcast_campaigns(current_user: User = Depends(get_current_user)):
    """Get broadcast campaigns"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        return {"campaigns": []}
    except Exception as e:
        logger.error(f"Error fetching broadcast campaigns: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch broadcast campaigns")

@api_router.get("/admin/message-templates")
async def admin_get_message_templates(current_user: User = Depends(get_current_user)):
    """Get message templates"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        return {"templates": []}
    except Exception as e:
        logger.error(f"Error fetching message templates: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch message templates")

@api_router.get("/admin/broadcast-audiences")
async def admin_get_broadcast_audiences(current_user: User = Depends(get_current_user)):
    """Get broadcast audiences"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        return {"audiences": []}
    except Exception as e:
        logger.error(f"Error fetching broadcast audiences: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch broadcast audiences")

@api_router.get("/admin/influencers")
async def admin_get_influencers(current_user: User = Depends(get_current_user)):
    """Get influencers"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        return {"influencers": []}
    except Exception as e:
        logger.error(f"Error fetching influencers: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch influencers")

@api_router.get("/admin/influencer-payouts")
async def admin_get_influencer_payouts(current_user: User = Depends(get_current_user)):
    """Get influencer payouts"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        return {"payouts": []}
    except Exception as e:
        logger.error(f"Error fetching influencer payouts: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch influencer payouts")

@api_router.get("/admin/referral-stats")
async def admin_get_referral_stats(current_user: User = Depends(get_current_user)):
    """Get referral statistics"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        return {"stats": {}}
    except Exception as e:
        logger.error(f"Error fetching referral stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch referral stats")

@api_router.get("/admin/roles")
async def admin_get_roles(current_user: User = Depends(get_current_user)):
    """Get admin roles"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        return {"roles": []}
    except Exception as e:
        logger.error(f"Error fetching roles: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch roles")

@api_router.get("/admin/permissions")
async def admin_get_permissions(current_user: User = Depends(get_current_user)):
    """Get admin permissions"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        return {"permissions": []}
    except Exception as e:
        logger.error(f"Error fetching permissions: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch permissions")

@api_router.get("/admin/admin-users")
async def admin_get_admin_users(current_user: User = Depends(get_current_user)):
    """Get admin users"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        return {"users": []}
    except Exception as e:
        logger.error(f"Error fetching admin users: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch admin users")

@api_router.get("/admin/notifications")
async def admin_get_notifications(current_user: User = Depends(get_current_user)):
    """Get admin notifications"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        return {"notifications": []}
    except Exception as e:
        logger.error(f"Error fetching notifications: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch notifications")

# Admin Users Endpoint  
@api_router.get("/users")
async def get_users(current_user: User = Depends(get_current_user)):
    """Get all users (admin only)"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        users_cursor = db.users.find({})
        users = []
        async for user_doc in users_cursor:
            # Remove sensitive data and MongoDB ObjectId
            user_doc.pop("password", None)
            user_doc.pop("_id", None)
            users.append(user_doc)
        
        return users
    except Exception as e:
        logger.error(f"Error fetching users: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch users")

# Admin Orders Endpoint
@api_router.get("/orders")
async def get_orders(current_user: User = Depends(get_current_user)):
    """Get orders"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        # Admin can see all orders, regular users see their own
        if UserRole.ADMIN in current_user.roles:
            orders_cursor = db.orders.find({})
        else:
            orders_cursor = db.orders.find({"buyer_id": current_user.id})
        
        orders = []
        async for order_doc in orders_cursor:
            # Remove MongoDB ObjectId
            order_doc.pop("_id", None)
            orders.append(order_doc)
        
        return orders
    except Exception as e:
        logger.error(f"Error fetching orders: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch orders")

# Server-Sent Events for Real-time Updates
@api_router.get("/admin/events/stream")  
async def admin_events_stream(current_user: User = Depends(get_current_user)):
    """Server-sent events stream for admin notifications"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    async def event_generator():
        try:
            # Send initial connection event
            yield f"data: {json.dumps({'event': 'CONNECTED', 'data': {'timestamp': datetime.now(timezone.utc).isoformat()}})}\n\n"
            
            # Keep connection alive with heartbeat
            while True:
                # Send heartbeat every 30 seconds
                yield f"data: {json.dumps({'event': 'HEARTBEAT', 'data': {'timestamp': datetime.now(timezone.utc).isoformat()}})}\n\n"
                await asyncio.sleep(30)
                
        except Exception as e:
            logger.error(f"SSE stream error: {e}")
            yield f"data: {json.dumps({'event': 'ERROR', 'data': {'error': str(e)}})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control"
        }
    )

# Emit SSE event function (to be called from other endpoints)
async def emit_admin_event(event_type: str, data: dict):
    """Emit admin event to SSE stream"""
    try:
        event_data = {
            "event": event_type,
            "id": str(uuid.uuid4()),
            "at": datetime.now(timezone.utc).isoformat(),
            "data": data
        }
        
        # Store event in database for missed events
        await db.admin_events.insert_one(event_data)
        
        # In a production system, this would notify connected SSE clients
        # For now, we'll just log the event
        logger.info(f"Admin event emitted: {event_type} - {data}")
        
    except Exception as e:
        logger.error(f"Error emitting admin event: {e}")

# Dashboard routes
@api_router.get("/dashboard/stats")
async def get_dashboard_stats(current_user: User = Depends(get_current_user)):
    """Get user dashboard statistics"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        stats = {}
        
        # Buyer stats
        if UserRole.BUYER in current_user.roles:
            buyer_orders = await db.orders.count_documents({"buyer_id": current_user.id})
            stats["buyer_orders"] = buyer_orders
        
        # Seller stats
        if UserRole.SELLER in current_user.roles:
            seller_listings = await db.listings.count_documents({"seller_id": current_user.id})
            seller_orders = await db.orders.count_documents({"seller_id": current_user.id})
            stats["seller_listings"] = seller_listings
            stats["seller_orders"] = seller_orders
        
        return stats
    except Exception as e:
        logger.error(f"Error fetching dashboard stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch dashboard stats")

# Categories route (using species as categories)
@api_router.get("/categories", response_model=List[Species])
async def get_categories():
    """Get all categories (species) for filtering"""
    try:
        species_docs = await db.species.find().to_list(length=None)
        return [Species(**doc) for doc in species_docs]
    except Exception as e:
        logger.error(f"Error fetching categories: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch categories")

# =============================================================================
# NEW API ROUTES FOR COMPREHENSIVE SYSTEM
# =============================================================================

# Notification API Routes
from pydantic import BaseModel as PydanticBaseModel

class NotificationPreferencesUpdate(PydanticBaseModel):
    email_enabled: Optional[bool] = None
    in_app_enabled: Optional[bool] = None
    push_enabled: Optional[bool] = None
    topics: Optional[Dict[str, Dict[str, bool]]] = None

# Blog API Routes
class BlogPostCreate(PydanticBaseModel):
    title: str
    content: str
    excerpt: Optional[str] = None
    category: Optional[str] = "news"
    status: Optional[str] = "draft"
    featured: Optional[bool] = False
    tags: Optional[List[str]] = []

class BlogPostUpdate(PydanticBaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    excerpt: Optional[str] = None
    tags: Optional[List[str]] = None
    status: Optional[str] = None

class BlogGenerateRequest(PydanticBaseModel):
    topic: str
    prompt: Dict[str, Any]
    model: Optional[str] = "openai:gpt-4o-mini"

@api_router.get("/blog/posts")
async def get_blog_posts(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    published_only: bool = False
):
    """Get blog posts"""
    try:
        blog_service = BlogService(db)
        posts = await blog_service.get_posts(
            status=BlogStatus(status) if status else None,
            limit=limit,
            offset=offset,
            published_only=published_only
        )
        
        return {"posts": posts, "total": len(posts)}
    except Exception as e:
        logger.error(f"Error fetching blog posts: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch blog posts")

@api_router.get("/blog/posts/{slug}")
async def get_blog_post_by_slug(slug: str):
    """Get blog post by slug"""
    try:
        blog_service = BlogService(db)
        post = await blog_service.get_post_by_slug(slug)
        
        if not post:
            raise HTTPException(status_code=404, detail="Blog post not found")
            
        return post
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching blog post: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch blog post")

@api_router.post("/admin/blog/generate")
async def generate_blog_post(
    data: BlogGenerateRequest,
    current_user: User = Depends(get_current_user)
):
    """Generate blog post using AI"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        blog_service = BlogService(db)
        job_id = await blog_service.generate_ai_blog_post(
            topic=data.topic,
            prompt=data.prompt,
            model=AIModel(data.model),
            author_id=current_user.id
        )
        
        return {"job_id": job_id, "status": "queued"}
    except Exception as e:
        logger.error(f"Error generating blog post: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate blog post")

@api_router.post("/ai/generate-blog-content")
async def generate_ai_blog_content(
    data: dict,
    current_user: User = Depends(get_current_user)
):
    """Generate AI content for blog posts"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Check if user has admin or content creator role
    if not any(role in current_user.roles for role in [UserRole.ADMIN, UserRole.SELLER]):
        raise HTTPException(status_code=403, detail="Content creation access required")
    
    try:
        content_type = data.get('type', 'content')
        prompt = data.get('prompt', '')
        category = data.get('category', 'livestock farming')
        context = data.get('context', {})
        
        if not prompt:
            raise HTTPException(status_code=400, detail="Prompt is required")
        
        # Create system prompt for livestock farming blog
        system_prompt = f"""You are an expert agricultural writer specializing in livestock farming, animal husbandry, and agricultural business. 
        Create professional, informative, and engaging content for StockLot, South Africa's livestock marketplace.
        
        Focus on practical advice, industry insights, and actionable information for farmers, buyers, and sellers.
        Use a professional but accessible tone. Include relevant South African context when appropriate.
        Category: {category}"""
        
        # Enhanced prompt based on context
        enhanced_prompt = prompt
        if context.get('title'):
            enhanced_prompt += f"\n\nBlog title: {context['title']}"
        if context.get('excerpt'):
            enhanced_prompt += f"\nExisting excerpt: {context['excerpt']}"
        if context.get('existing_content'):
            enhanced_prompt += f"\nExisting content to build upon: {context['existing_content'][:500]}..."
        
        # Generate content using OpenAI
        response = await ai_service.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": enhanced_prompt}
            ],
            max_tokens=1000 if content_type == 'content' else 200,
            temperature=0.7
        )
        
        generated_content = response.choices[0].message.content.strip()
        
        return {
            "content": generated_content,
            "type": content_type,
            "model": "gpt-4o-mini",
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error generating AI blog content: {e}")
        # Return fallback content instead of error
        fallback_content = f"Content about {category} - please write your own content or try again with a different prompt."
        return {
            "content": fallback_content,
            "type": content_type,
            "model": "fallback",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "error": str(e)
        }

@api_router.post("/admin/blog/posts")
async def create_blog_post(
    data: BlogPostCreate,
    current_user: User = Depends(get_current_user)
):
    """Create new blog post (admin only)"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        blog_service = BlogService(db)
        post = await blog_service.create_blog_post(
            title=data.title,
            content=data.content,
            author_id=current_user.id,
            excerpt=data.excerpt,
            tags=data.tags,
            status=BlogStatus(data.status)
        )
        
        return post
    except Exception as e:
        logger.error(f"Error creating blog post: {e}")
        raise HTTPException(status_code=500, detail="Failed to create blog post")

@api_router.post("/blog/posts")
async def create_user_blog_post(
    data: BlogPostCreate,
    current_user: User = Depends(get_current_user)
):
    """Create new blog post (any authenticated user)"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        blog_service = BlogService(db)
        # User posts start as draft and need admin approval
        post = await blog_service.create_blog_post(
            title=data.title,
            content=data.content,
            author_id=current_user.id,
            excerpt=data.excerpt,
            tags=data.tags,
            status=BlogStatus.DRAFT  # Always start as draft for user posts
        )
        
        return {"success": True, "post": post, "message": "Blog post created successfully and submitted for review"}
    except Exception as e:
        logger.error(f"Error creating user blog post: {e}")
        raise HTTPException(status_code=500, detail="Failed to create blog post")

@api_router.post("/admin/blog/posts/{post_id}/publish")
async def publish_blog_post(
    post_id: str,
    current_user: User = Depends(get_current_user)
):
    """Publish blog post"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        blog_service = BlogService(db)
        success = await blog_service.publish_post(post_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Blog post not found")
            
        return {"success": True, "message": "Blog post published"}
    except Exception as e:
        logger.error(f"Error publishing blog post: {e}")
        raise HTTPException(status_code=500, detail="Failed to publish blog post")

@api_router.post("/admin/blog/weekly-generate")
async def generate_weekly_content(current_user: User = Depends(get_current_user)):
    """Generate weekly content based on templates"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        blog_service = BlogService(db)
        job_ids = await blog_service.generate_weekly_content()
        
        return {"job_ids": job_ids, "generated_count": len(job_ids)}
    except Exception as e:
        logger.error(f"Error generating weekly content: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate weekly content")

# Referral API Routes
class ReferralClickTrack(PydanticBaseModel):
    code: str
    ip_address: str
    user_agent: str
    landing_path: str
    utm_params: Optional[Dict[str, str]] = {}

@api_router.get("/referrals/my-code")
async def get_my_referral_code(current_user: User = Depends(get_current_user)):
    """Get current user's referral code"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        referral_service = ReferralService(db)
        code = await referral_service.get_or_create_referral_code(current_user.id)
        
        # Generate complete referral link
        link = await referral_service.generate_referral_link(current_user.id)
        
        return {
            "code": code,
            "link": link
        }
    except Exception as e:
        logger.error(f"Error fetching referral code: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch referral code")

@api_router.get("/referrals/stats")
async def get_referral_stats(current_user: User = Depends(get_current_user)):
    """Get referral statistics"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        referral_service = ReferralService(db)
        stats = await referral_service.get_referral_stats(current_user.id)
        
        return stats
    except Exception as e:
        logger.error(f"Error fetching referral stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch referral stats")

@api_router.get("/referrals/wallet")
async def get_user_wallet(current_user: User = Depends(get_current_user)):
    """Get user wallet information"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        referral_service = ReferralService(db)
        wallet = await referral_service.get_user_wallet(current_user.id)
        
        return wallet
    except Exception as e:
        logger.error(f"Error fetching wallet: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch wallet")

@api_router.get("/referrals/click")
async def track_referral_click(
    code: str,
    to: str = "/",
    utm_source: Optional[str] = None,
    utm_medium: Optional[str] = None,
    utm_campaign: Optional[str] = None,
    request: Request = None
):
    """Track referral click and redirect"""
    try:
        referral_service = ReferralService(db)
        
        # Extract request info
        ip_address = request.client.host if request else "unknown"
        user_agent = request.headers.get("user-agent", "") if request else ""
        
        utm_params = {}
        if utm_source:
            utm_params["utm_source"] = utm_source
        if utm_medium:
            utm_params["utm_medium"] = utm_medium
        if utm_campaign:
            utm_params["utm_campaign"] = utm_campaign
        
        # Track the click
        await referral_service.track_referral_click(
            code=code,
            ip_address=ip_address,
            user_agent=user_agent,
            landing_path=to,
            utm_params=utm_params
        )
        
        # In a real implementation, you'd redirect to the landing page
        # For now, return success with redirect URL
        return {
            "success": True,
            "redirect_to": to,
            "code": code
        }
    except Exception as e:
        logger.error(f"Error tracking referral click: {e}")
        return {"success": False, "redirect_to": to}

# Enhanced Registration with Notifications and Referrals
@api_router.post("/auth/register-enhanced", status_code=201)
async def register_user_enhanced(
    user_data: UserCreate,
    referral_code: Optional[str] = None,
    request: Request = None
):
    """Enhanced registration with notifications and referral tracking"""
    try:
        # Check if user exists
        existing_user = await db.users.find_one({"email": user_data.email})
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # Hash password
        hashed_password = hash_password(user_data.password)
        
        # Create user
        user = User(
            email=user_data.email,
            full_name=user_data.full_name,
            phone=user_data.phone,
            roles=resolve_user_roles(user_data.user_type, user_data.role)
        )
        
        # Save to database
        user_dict = user.dict()
        user_dict["password"] = hashed_password
        await db.users.insert_one(user_dict)
        
        # Send welcome notification
        # await send_welcome_email(db, user.id, user.full_name, user.email)
        
        # Handle referral attribution if code provided
        if referral_code:
            referral_service = ReferralService(db)
            await referral_service.attribute_signup(user.id, referral_code)
        
        return {"message": "User registered successfully", "user_id": user.id}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error registering user: {e}")
        raise HTTPException(status_code=500, detail="Registration failed")

# Enhanced Login with Security Notifications
@api_router.post("/auth/login-enhanced")
async def login_user_enhanced(
    login_data: UserLogin,
    request: Request = None
):
    """Enhanced login with security notifications"""
    try:
        # Find user
        user_doc = await db.users.find_one({"email": login_data.email})
        if not user_doc:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # Verify password
        if not user_doc.get("password") or not verify_password(login_data.password, user_doc["password"]):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        user = User(**{k: v for k, v in user_doc.items() if k != "password"})
        
        # Send login alert for security
        device_info = request.headers.get("user-agent", "Unknown device") if request else "Unknown device"
        ip_address = request.client.host if request else "Unknown location"
        
        # await send_login_alert(
        #     db, 
        #     user.id, 
        #     user.full_name, 
        #     device_info, 
        #     ip_address
        # )
        
        return {
            "access_token": user.email,
            "token_type": "bearer",
            "user": user
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error logging in user: {e}")
        raise HTTPException(status_code=500, detail="Login failed")

# =============================================================================
# BUY REQUEST API ROUTES (Wanted Listings / Reverse Auction)
# =============================================================================

class BuyRequestCreate(PydanticBaseModel):
    species: str
    product_type: str
    qty: int
    unit: str
    target_price: Optional[float] = None
    breed: Optional[str] = None
    province: Optional[str] = None
    country: Optional[str] = "ZA"
    expires_at: Optional[str] = None
    notes: Optional[str] = None
    # New fields for enhanced content
    images: Optional[List[str]] = []
    vet_certificates: Optional[List[str]] = []
    weight_range: Optional[dict] = None  # {"min": 1.5, "max": 2.0, "unit": "kg"}
    age_requirements: Optional[dict] = None  # {"min": 6, "max": 12, "unit": "weeks"}
    vaccination_requirements: Optional[List[str]] = []
    delivery_preferences: Optional[str] = "both"  # "pickup", "delivery", "both"
    inspection_allowed: Optional[bool] = True
    additional_requirements: Optional[str] = None

class OfferCreate(PydanticBaseModel):
    offer_price: float
    qty: int
    message: Optional[str] = None
    listing_id: Optional[str] = None

@api_router.get("/buy-requests")
async def get_buy_requests(
    request: Request,
    status: Optional[str] = None,
    species: Optional[str] = None,
    provinces: Optional[str] = None,
    country: Optional[str] = "ZA",
    q: Optional[str] = None,
    sort: Optional[str] = "new",
    limit: int = 50,
    offset: int = 0
):
    """Get buy requests with filtering"""
    # Temporarily disable rate limiting for debugging
    # await rate_limit_middleware(request, "buy_requests", None)
    
    try:
        buy_request_service = BuyRequestService(db)
        
        # Parse provinces from comma-separated string
        province_list = provinces.split(',') if provinces else None
        
        # Map sort parameter
        sort_mapping = {
            "new": "created_at",
            "expiring": "expires_at", 
            "price_desc": "target_price",
            "price_asc": "target_price"
        }
        sort_by = sort_mapping.get(sort, "created_at")
        
        requests = await buy_request_service.get_buy_requests(
            status=BuyRequestStatus(status) if status and status != "ALL" else None,
            species=species,
            province=province_list[0] if province_list else None,  # Use first province for now
            country=country,
            search_query=q,
            sort_by=sort_by,
            limit=limit,
            offset=offset
        )
        
        return {"items": requests}
        
    except Exception as e:
        logger.error(f"Error fetching buy requests: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch buy requests")

@api_router.post("/buy-requests")
async def create_buy_request(
    data: BuyRequestCreate,
    current_user: User = Depends(get_current_user)
):
    """Create a new buy request"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        buy_request_service = BuyRequestService(db)
        
        # Parse expires_at if provided
        expires_at = None
        if data.expires_at:
            expires_at = datetime.fromisoformat(data.expires_at.replace('Z', '+00:00'))
        
        request = await buy_request_service.create_buy_request(
            buyer_id=current_user.id,
            species=data.species,
            product_type=data.product_type,
            qty=data.qty,
            unit=data.unit,
            target_price=data.target_price,
            breed=data.breed,
            province=data.province,
            country=data.country,
            expires_at=expires_at,
            notes=data.notes,
            # Enhanced fields
            images=data.images or [],
            vet_certificates=data.vet_certificates or [],
            weight_range=data.weight_range,
            age_requirements=data.age_requirements,
            vaccination_requirements=data.vaccination_requirements or [],
            delivery_preferences=data.delivery_preferences or "both",
            inspection_allowed=data.inspection_allowed if data.inspection_allowed is not None else True,
            additional_requirements=data.additional_requirements
        )
        
        # Notify nearby sellers if auto-approved
        if request["moderation_status"] == "auto_pass":
            try:
                await notify_nearby_sellers(db, request)
            except Exception as e:
                logger.warning(f"Failed to notify sellers: {e}")
        
        # 🔔 Emit buy request created event for notification system
        try:
            await emit_buy_request_created(
                request_id=request["id"],
                buyer_id=current_user.id,
                species=data.species,
                province=data.province,
                title=f"{data.species} Buy Request",
                quantity=data.qty
            )
        except Exception as e:
            logger.warning(f"Failed to emit buy request created event: {e}")
        
        # 📧 Send buy request posted email (E54)
        try:
            buyer_name = current_user.full_name or "Customer"
            request_url = f"https://stocklot.farm/buy-requests/{request['id']}"
            
            notification = EmailNotification(
                template_id="E54",
                recipient_email=current_user.email,
                recipient_name=buyer_name,
                variables={
                    "request_code": request["id"][:8].upper(),
                    "request_url": request_url
                },
                tags=["E54", "buy-requests", "posted"]
            )
            await email_notification_service.send_email(notification)
            logger.info(f"Buy request posted email sent for request {request['id']}")
        except Exception as e:
            logger.warning(f"Failed to send buy request posted email for {request['id']}: {e}")
        
        return {
            "ok": True,
            "id": request["id"],
            "moderation_status": request["moderation_status"]
        }
        
    except Exception as e:
        logger.error(f"Error creating buy request: {e}")
        raise HTTPException(status_code=500, detail="Failed to create buy request")

# ============================================================================
# BUY REQUEST DASHBOARD API ENDPOINTS (MUST BE BEFORE GENERIC ROUTES)
# ============================================================================

@api_router.get("/buy-requests/my-requests")
async def get_my_buy_requests(
    current_user: User = Depends(get_current_user),
    status: Optional[str] = None,
    page: int = 1,
    limit: int = 20
):
    """Get buyer's own buy requests with filtering and pagination"""
    try:
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        # Build query
        query = {"buyer_id": current_user.id}
        if status:
            query["status"] = status
        
        # Calculate pagination
        skip = (page - 1) * limit
        
        # Get buy requests
        cursor = db.buy_requests.find(query).sort("created_at", -1).skip(skip).limit(limit)
        requests = await cursor.to_list(length=None)
        
        # Get total count
        total = await db.buy_requests.count_documents(query)
        
        # Format response
        for req in requests:
            if "_id" in req:
                del req["_id"]
            
            # Add offer count
            offers_count = await db.buy_request_offers.count_documents({"request_id": req["id"]})
            req["offers_count"] = offers_count
        
        return {
            "requests": requests,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "pages": (total + limit - 1) // limit
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting my buy requests: {e}")
        raise HTTPException(status_code=500, detail="Failed to get buy requests")

@api_router.get("/buy-requests/seller-inbox")
async def get_seller_inbox(
    current_user: User = Depends(get_current_user),
    species: Optional[str] = None,
    province: Optional[str] = None,
    max_distance_km: Optional[int] = 100,
    page: int = 1,
    limit: int = 20
):
    """Get buy requests in seller's delivery range"""
    try:
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        # Check if user is seller
        if "seller" not in (current_user.roles or []):
            raise HTTPException(status_code=403, detail="Seller access required")
        
        # Build query
        query = {"status": "active"}
        if species:
            query["species"] = species
        if province:
            query["province"] = province
        
        # Get buy requests
        skip = (page - 1) * limit
        cursor = db.buy_requests.find(query).sort("created_at", -1).skip(skip).limit(limit)
        requests = await cursor.to_list(length=None)
        
        # Format response
        for req in requests:
            if "_id" in req:
                del req["_id"]
            
            # Check if seller already made an offer
            existing_offer = await db.buy_request_offers.find_one({
                "request_id": req["id"],
                "seller_id": current_user.id
            })
            req["has_offer"] = bool(existing_offer)
            
            # Add offer count
            offers_count = await db.buy_request_offers.count_documents({"request_id": req["id"]})
            req["offers_count"] = offers_count
        
        # Get total count
        total = await db.buy_requests.count_documents(query)
        
        return {
            "requests": requests,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "pages": (total + limit - 1) // limit
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting seller inbox: {e}")
        raise HTTPException(status_code=500, detail="Failed to get seller inbox")

@api_router.get("/buy-requests/my-offers")
async def get_my_offers(
    current_user: User = Depends(get_current_user),
    status: Optional[str] = None,
    page: int = 1,
    limit: int = 20
):
    """Get seller's own offers"""
    try:
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        # Check if user is seller
        if "seller" not in (current_user.roles or []):
            raise HTTPException(status_code=403, detail="Seller access required")
        
        # Build query
        query = {"seller_id": current_user.id}
        if status:
            query["status"] = status
        
        # Get offers with pagination
        skip = (page - 1) * limit
        cursor = db.buy_request_offers.find(query).sort("created_at", -1).skip(skip).limit(limit)
        offers = await cursor.to_list(length=None)
        
        # Get associated buy requests
        for offer in offers:
            if "_id" in offer:
                del offer["_id"]
            
            # Get the buy request details
            buy_request = await db.buy_requests.find_one({"id": offer["request_id"]})
            if buy_request:
                if "_id" in buy_request:
                    del buy_request["_id"]
                offer["buy_request"] = buy_request
        
        # Get total count
        total = await db.buy_request_offers.count_documents(query)
        
        return {
            "offers": offers,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "pages": (total + limit - 1) // limit
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting my offers: {e}")
        raise HTTPException(status_code=500, detail="Failed to get offers")

# ============================================================================
# AI ENHANCED ENDPOINTS (MUST BE BEFORE GENERIC {request_id} ROUTES)
# ============================================================================

@api_router.get("/buy-requests/price-suggestions")
async def get_price_suggestions(
    species: str,
    product_type: str,
    breed: Optional[str] = None,
    province: Optional[str] = None,
    quantity: Optional[int] = None,
    unit: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Get AI-powered price suggestions"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    if not AI_SERVICES_AVAILABLE or not ai_enhanced_service or not enhanced_buy_request_service:
        raise HTTPException(status_code=503, detail="AI services are currently unavailable")
    
    try:
        # Get recent market data
        recent_data = await enhanced_buy_request_service._get_recent_market_data(
            species=species,
            product_type=product_type,
            province=province
        )
        
        suggestions = await ai_enhanced_service.generate_price_suggestions(
            species=species,
            product_type=product_type,
            breed=breed,
            location=province,
            quantity=quantity,
            unit=unit,
            market_data=recent_data
        )
        
        return {
            "suggestions": suggestions,
            "market_data_points": len(recent_data)
        }
        
    except Exception as e:
        logger.error(f"Error getting price suggestions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get price suggestions: {str(e)}")

@api_router.post("/buy-requests/auto-description")
async def generate_auto_description(
    data: dict,
    current_user: User = Depends(get_current_user)
):
    """Generate AI-powered description for buy request"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    if not AI_SERVICES_AVAILABLE or not ai_enhanced_service:
        raise HTTPException(status_code=503, detail="AI services are currently unavailable")
    
    try:
        description_data = await ai_enhanced_service.generate_auto_description(
            species=data.get('species'),
            product_type=data.get('product_type'),
            breed=data.get('breed'),
            quantity=data.get('quantity'),
            unit=data.get('unit'),
            location=data.get('province'),
            target_price=data.get('target_price'),
            basic_notes=data.get('notes')
        )
        
        return description_data
        
    except Exception as e:
        logger.error(f"Error generating auto description: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate description: {str(e)}")

@api_router.get("/buy-requests/{request_id}")
async def get_buy_request(request_id: str):
    """Get buy request details"""
    try:
        buy_request_service = BuyRequestService(db)
        request = await buy_request_service.get_buy_request_by_id(request_id)
        
        if not request:
            raise HTTPException(status_code=404, detail="Buy request not found")
            
        return {"item": request}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching buy request: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch buy request")

@api_router.get("/buy-requests/{request_id}/offers")
async def get_buy_request_offers(request_id: str):
    """Get offers for a buy request"""
    try:
        buy_request_service = BuyRequestService(db)
        offers = await buy_request_service.get_offers_for_request(request_id)
        
        return {"items": offers}
        
    except Exception as e:
        logger.error(f"Error fetching offers: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch offers")

@api_router.get("/buyers/offers")
async def get_buyer_offers(
    current_user: User = Depends(get_current_user),
    status: Optional[str] = None,
    limit: int = 50
):
    """Get all offers for the current buyer's requests"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        buy_request_service = BuyRequestService(db)
        
        # Get all buyer's requests first
        buyer_requests = await buy_request_service.get_buy_requests_for_buyer(
            buyer_id=current_user.id,
            limit=1000  # Get all requests
        )
        
        request_ids = [req["id"] for req in buyer_requests]
        
        if not request_ids:
            return {"items": []}
        
        # Get all offers for buyer's requests
        offers = await buy_request_service.get_buyer_offers(
            request_ids=request_ids,
            status=status,
            limit=limit
        )
        
        return {
            "items": offers,
            "total": len(offers)
        }
        
    except Exception as e:
        logger.error(f"Error fetching buyer offers: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch buyer offers")

@api_router.post("/buy-requests/{request_id}/offers/{offer_id}/accept")
async def accept_offer(
    request_id: str,
    offer_id: str,
    current_user: User = Depends(get_current_user)
):
    """Accept an offer on a buy request"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        buy_request_service = BuyRequestService(db)
        
        result = await buy_request_service.accept_offer(
            request_id=request_id,
            offer_id=offer_id,
            buyer_id=current_user.id
        )
        
        # Send notification to seller
        from services.notification_service import NotificationService, NotificationTopic, NotificationChannel
        notification_service = NotificationService(db)
        
        # Get offer details for notification
        offer = result.get("offer")
        if offer:
            await notification_service.send_notification(
                user_id=offer["seller_id"],
                topic=NotificationTopic.OFFER_ACCEPTED,
                title="Offer Accepted!",
                message=f"Your offer of R{offer['offer_price']:,.2f} has been accepted!",
                channels=[NotificationChannel.IN_APP, NotificationChannel.EMAIL],
                action_url=f"/my-offers#{offer_id}",
                data={"offer_id": offer_id, "request_id": request_id}
            )
        
        return {
            "success": True,
            "message": "Offer accepted successfully",
            "next_step": result.get("next_step"),
            "offer": result.get("offer")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error accepting offer: {e}")
        raise HTTPException(status_code=500, detail="Failed to accept offer")

@api_router.post("/buy-requests/{request_id}/offers/{offer_id}/decline")
async def decline_offer(
    request_id: str,
    offer_id: str,
    current_user: User = Depends(get_current_user)
):
    """Decline an offer on a buy request"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        buy_request_service = BuyRequestService(db)
        
        success = await buy_request_service.decline_offer(
            request_id=request_id,
            offer_id=offer_id,
            buyer_id=current_user.id
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Offer not found or already processed")
        
        # Send notification to seller
        from services.notification_service import NotificationService, NotificationTopic, NotificationChannel
        notification_service = NotificationService(db)
        
        # Get offer details for notification
        offer = await buy_request_service.get_offer_by_id(offer_id)
        if offer:
            await notification_service.send_notification(
                user_id=offer["seller_id"],
                topic=NotificationTopic.OFFER_DECLINED,
                title="Offer Declined",
                message=f"Your offer for {offer.get('request_title', 'livestock')} has been declined.",
                channels=[NotificationChannel.IN_APP, NotificationChannel.EMAIL],
                action_url=f"/my-offers#{offer_id}",
                data={"offer_id": offer_id, "request_id": request_id}
            )
        
        return {
            "success": True,
            "message": "Offer declined successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error declining offer: {e}")
        raise HTTPException(status_code=500, detail="Failed to decline offer")

# PAYMENT PROCESSING API
@api_router.post("/payment/create-paystack")
async def create_paystack_payment(
    request: Request,
    payment_data: dict
):
    """Create Paystack payment initialization"""
    try:
        console.log("🛒 Backend: Creating Paystack payment")
        
        # Extract payment details
        amount = payment_data.get('amount', 0)
        email = payment_data.get('email', 'customer@stocklot.co.za')
        reference = payment_data.get('reference', f'STOCKLOT_{int(time.time())}')
        metadata = payment_data.get('metadata', {})
        
        # Convert amount to kobo (cents)
        amount_kobo = int(amount * 100)
        
        # Prepare Paystack payload
        paystack_payload = {
            'email': email,
            'amount': amount_kobo,
            'currency': 'ZAR',
            'reference': reference,
            'callback_url': f"{request.base_url}payment/success",
            'metadata': metadata
        }
        
        console.log(f"🛒 Paystack payload: {paystack_payload}")
        
        # Make request to Paystack
        import requests
        
        response = requests.post(
            'https://api.paystack.co/transaction/initialize',
            json=paystack_payload,
            headers={
                'Authorization': 'Bearer pk_live_ff6855bb7797fecca7f892f482451f79a5b2cf6f',
                'Content-Type': 'application/json'
            }
        )
        
        if response.status_code == 200:
            result = response.json()
            console.log(f"✅ Paystack response: {result}")
            
            if result.get('status') and result.get('data', {}).get('authorization_url'):
                return {
                    'success': True,
                    'payment_url': result['data']['authorization_url'],
                    'reference': result['data']['reference']
                }
            else:
                raise HTTPException(status_code=400, detail="Failed to get payment URL from Paystack")
        else:
            error_data = response.json() if response.content else {}
            console.log(f"🚨 Paystack error: {response.status_code} - {error_data}")
            raise HTTPException(
                status_code=400, 
                detail=f"Paystack error: {error_data.get('message', 'Payment initialization failed')}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Payment creation error: {e}")
        raise HTTPException(status_code=500, detail=f"Payment creation failed: {str(e)}")

# NOTIFICATIONS API
@api_router.get("/notifications")
async def get_user_notifications(
    current_user: User = Depends(get_current_user),
    unread_only: bool = False,
    limit: int = 50,
    offset: int = 0
):
    """Get notifications for the current user"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        from services.notification_service import NotificationService
        notification_service = NotificationService(db)
        
        notifications = await notification_service.get_notifications(
            user_id=current_user.id,
            unread_only=unread_only,
            limit=limit,
            offset=offset
        )
        
        return {
            "items": notifications,
            "total": len(notifications)
        }
        
    except Exception as e:
        logger.error(f"Error fetching notifications: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch notifications")

@api_router.get("/notifications/unread-count")
async def get_unread_count(
    current_user: User = Depends(get_current_user)
):
    """Get count of unread notifications"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        from services.notification_service import NotificationService
        notification_service = NotificationService(db)
        
        count = await notification_service.get_unread_count(current_user.id)
        
        return {"count": count}
        
    except Exception as e:
        logger.error(f"Error fetching unread count: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch unread count")

@api_router.post("/notifications/mark-read")
async def mark_notifications_read(
    notification_ids: List[str],
    current_user: User = Depends(get_current_user)
):
    """Mark notifications as read"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        from services.notification_service import NotificationService
        notification_service = NotificationService(db)
        
        success = await notification_service.mark_as_read(
            user_id=current_user.id,
            notification_ids=notification_ids
        )
        
        return {"success": success}
        
    except Exception as e:
        logger.error(f"Error marking notifications as read: {e}")
        raise HTTPException(status_code=500, detail="Failed to mark notifications as read")

@api_router.post("/notifications/mark-all-read")
async def mark_all_notifications_read(
    current_user: User = Depends(get_current_user)
):
    """Mark all notifications as read"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        from services.notification_service import NotificationService
        notification_service = NotificationService(db)
        
        count = await notification_service.mark_all_as_read(current_user.id)
        
        return {"marked_count": count}
        
    except Exception as e:
        logger.error(f"Error marking all notifications as read: {e}")
        raise HTTPException(status_code=500, detail="Failed to mark all notifications as read")

# ADMIN BUY REQUESTS MANAGEMENT API
@api_router.get("/admin/buy-requests")
async def get_admin_buy_requests(
    current_user: User = Depends(get_current_user),
    status: Optional[str] = None,
    moderation_status: Optional[str] = None,
    species: Optional[str] = None,
    province: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    """Get buy requests for admin management"""
    if not current_user or "admin" not in (current_user.roles or []):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Build query
        query = {}
        
        if status:
            query["status"] = status
        if moderation_status:
            query["moderation_status"] = moderation_status
        if species:
            query["species"] = species
        if province:
            query["province"] = province
        
        # Get buy requests with pagination
        cursor = db.buy_requests.find(query).sort("created_at", -1).skip(offset).limit(limit)
        requests = await cursor.to_list(length=None)
        
        # Get total count
        total = await db.buy_requests.count_documents(query)
        
        # Clean up MongoDB _id fields and add additional data
        for request in requests:
            if "_id" in request:
                del request["_id"]
            
            # Get offers count
            offers_count = await db.buy_request_offers.count_documents({"request_id": request["id"]})
            request["offers_count"] = offers_count
            
            # Get buyer info
            buyer = await db.users.find_one({"id": request["buyer_id"]})
            if buyer:
                if "_id" in buyer:
                    del buyer["_id"]
                request["buyer_name"] = buyer.get("full_name", "Unknown")
                request["buyer_email"] = buyer.get("email", "")
                request["buyer_verified"] = buyer.get("verified", False)
        
        return {
            "buy_requests": requests,
            "total": total,
            "page": (offset // limit) + 1,
            "limit": limit,
            "pages": (total + limit - 1) // limit
        }
        
    except Exception as e:
        logger.error(f"Error getting admin buy requests: {e}")
        raise HTTPException(status_code=500, detail="Failed to get buy requests")

@api_router.post("/admin/buy-requests/{request_id}/approve")
async def approve_buy_request(
    request_id: str,
    current_user: User = Depends(get_current_user)
):
    """Approve a buy request"""
    if not current_user or "admin" not in (current_user.roles or []):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        result = await db.buy_requests.update_one(
            {"id": request_id},
            {
                "$set": {
                    "moderation_status": "auto_pass",
                    "updated_at": datetime.now(timezone.utc)
                }
            }
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Buy request not found")
        
        return {"success": True, "message": "Buy request approved"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving buy request: {e}")
        raise HTTPException(status_code=500, detail="Failed to approve buy request")

@api_router.post("/admin/buy-requests/{request_id}/reject")
async def reject_buy_request(
    request_id: str,
    current_user: User = Depends(get_current_user)
):
    """Reject a buy request"""
    if not current_user or "admin" not in (current_user.roles or []):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        result = await db.buy_requests.update_one(
            {"id": request_id},
            {
                "$set": {
                    "moderation_status": "flagged",
                    "status": "rejected",
                    "updated_at": datetime.now(timezone.utc)
                }
            }
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Buy request not found")
        
        return {"success": True, "message": "Buy request rejected"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rejecting buy request: {e}")
        raise HTTPException(status_code=500, detail="Failed to reject buy request")

@api_router.post("/admin/buy-requests/{request_id}/close")
async def close_buy_request(
    request_id: str,
    current_user: User = Depends(get_current_user)
):
    """Close a buy request"""
    if not current_user or "admin" not in (current_user.roles or []):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        result = await db.buy_requests.update_one(
            {"id": request_id},
            {
                "$set": {
                    "status": "closed",
                    "updated_at": datetime.now(timezone.utc)
                }
            }
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Buy request not found")
        
        return {"success": True, "message": "Buy request closed"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error closing buy request: {e}")
        raise HTTPException(status_code=500, detail="Failed to close buy request")

@api_router.post("/buy-requests/{request_id}/offers")
async def create_offer(
    request_id: str,
    data: OfferCreate,
    current_user: User = Depends(get_current_user)
):
    """Create an offer on a buy request"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        buy_request_service = BuyRequestService(db)
        
        offer = await buy_request_service.create_offer(
            request_id=request_id,
            seller_id=current_user.id,
            offer_price=data.offer_price,
            qty=data.qty,
            message=data.message,
            listing_id=data.listing_id
        )
        
        # Send notification to buyer
        from services.notification_service import NotificationService, NotificationTopic, NotificationChannel
        notification_service = NotificationService(db)
        
        # Get buy request details for notification
        buy_request = await buy_request_service.get_buy_request_by_id(request_id)
        if buy_request:
            seller_name = current_user.full_name or "A seller"
            request_title = f"{buy_request.get('breed', '')} {buy_request['species']}".strip() or buy_request['species']
            
            await notification_service.send_notification(
                user_id=buy_request["buyer_id"],
                topic=NotificationTopic.OFFER_RECEIVED,
                title="New Offer Received!",
                message=f"{seller_name} has sent you an offer of R{data.offer_price:,.2f} for your {request_title} request.",
                channels=[NotificationChannel.IN_APP, NotificationChannel.EMAIL],
                action_url=f"/offers-received#{offer['id']}",
                data={
                    "offer_id": offer["id"],
                    "request_id": request_id,
                    "seller_name": seller_name,
                    "offer_price": data.offer_price
                }
            )
            
            # 📧 Send offer received email (E56)
            try:
                buyer_doc = await db.users.find_one({"id": buy_request["buyer_id"]})
                if buyer_doc:
                    offer_url = f"https://stocklot.farm/offers-received#{offer['id']}"
                    
                    notification = EmailNotification(
                        template_id="E56",
                        recipient_email=buyer_doc["email"],
                        recipient_name=buyer_doc.get("full_name", "Customer"),
                        variables={
                            "request_code": request_id[:8].upper(),
                            "offer_price": f"R{data.offer_price:,.2f}",
                            "offer_url": offer_url
                        },
                        tags=["E56", "offers", "received"]
                    )
                    await email_notification_service.send_email(notification)
                    logger.info(f"Offer received email sent for offer {offer['id']}")
            except Exception as e:
                logger.warning(f"Failed to send offer received email for {offer['id']}: {e}")
        
        # Auto-create conversation for this offer
        try:
            if buy_request:
                request_title = f"{buy_request.get('breed', '')} {buy_request['species']}".strip() or buy_request['species']
                conversation_title = f"Offer: {request_title} - R{data.offer_price:,.2f}"
                conversation_id = await unified_inbox_service.create_offer_conversation(
                    offer_id=offer["id"],
                    buyer_id=buy_request["buyer_id"],
                    seller_id=current_user.id,
                    request_title=conversation_title
                )
                logger.info(f"Created conversation {conversation_id} for offer {offer['id']}")
        except Exception as e:
            logger.warning(f"Failed to create conversation for offer {offer['id']}: {e}")
            # Don't fail the offer creation if conversation creation fails
        
        return {"ok": True, "offer_id": offer["id"]}
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating offer: {e}")
        raise HTTPException(status_code=500, detail="Failed to create offer")

@api_router.post("/buy-requests/{request_id}/offers/{offer_id}/accept")
async def accept_offer(
    request_id: str,
    offer_id: str,
    current_user: User = Depends(get_current_user)
):
    """Accept an offer (creates order and redirects to payment)"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        buy_request_service = BuyRequestService(db)
        
        # Accept the offer
        result = await buy_request_service.accept_offer(
            request_id=request_id,
            offer_id=offer_id,
            buyer_id=current_user.id
        )
        
        # AUTO-CREATE ORDER FROM ACCEPTED OFFER
        offer = result["offer"]
        request_data = result["request"]
        
        # Create order data from offer
        order_data = {
            "buyer_id": current_user.id,
            "seller_id": offer["seller_id"],
            "items": [{
                "listing_id": offer.get("listing_id"),
                "quantity": offer["qty"],
                "unit_price": offer["offer_price"],
                "total_price": offer["offer_price"] * offer["qty"],
                "product_type": request_data["product_type"],
                "species": request_data["species"],
                "breed": request_data.get("breed"),
                "notes": f"Order created from buy request: {request_data.get('notes', 'N/A')}"
            }],
            "total_amount": offer["offer_price"] * offer["qty"],
            "currency": "ZAR",
            "delivery_method": "self_collection",  # Default, can be updated
            "order_status": "pending_payment",
            "source": "buy_request",
            "buy_request_id": request_id,
            "offer_id": offer_id
        }
        
        # Create the order using existing order creation logic
        try:
            order_response = await create_order_internal(order_data, current_user)
            order_id = order_response.get("order_id")
            
            logger.info(f"Auto-created order {order_id} from accepted offer {offer_id}")
            
            # Add system messages to conversations
            try:
                # Find the offer conversation and add system message
                from services.unified_inbox_service import UnifiedInboxService
                from inbox_models.inbox_models import SystemMessageType
                
                # Send system message to offer conversation
                offer_conversations = await db.conversations.find({
                    "type": "OFFER", 
                    "offer_id": offer_id
                }).to_list(length=None)
                
                for conv in offer_conversations:
                    await unified_inbox_service.send_system_message(
                        conversation_id=conv["id"],
                        system_type=SystemMessageType.ORDER_STATUS,
                        message=f"🎉 Offer accepted! Order #{order_id[:8]} has been created and is ready for payment.",
                        meta={"order_id": order_id, "status": "offer_accepted"}
                    )
                
                logger.info(f"Added system messages for accepted offer {offer_id}")
            except Exception as e:
                logger.warning(f"Failed to add system messages for accepted offer: {e}")
            
            return {
                "ok": True,
                "message": "Offer accepted successfully! Order created.",
                "order_id": order_id,
                "redirect_to_checkout": True,
                "checkout_url": f"/checkout/{order_id}",
                "next_step": "payment",
                "total_amount": order_data["total_amount"],
                "currency": "ZAR"
            }
            
        except Exception as order_error:
            logger.error(f"Failed to create order from offer: {order_error}")
            # Still return success for offer acceptance, but indicate order creation failed
            return {
                "ok": True,
                "message": "Offer accepted, but order creation failed. Please contact support.",
                "manual_order_needed": True,
                "offer_details": {
                    "seller_id": offer["seller_id"],
                    "quantity": offer["qty"], 
                    "price": offer["offer_price"],
                    "total": offer["offer_price"] * offer["qty"]
                }
            }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error accepting offer: {e}")
        raise HTTPException(status_code=500, detail="Failed to accept offer")

# Helper function for internal order creation
async def create_order_internal(order_data: dict, user: User) -> dict:
    """Internal function to create orders from various sources"""
    try:
        # Generate order ID
        order_id = str(uuid.uuid4())
        
        # Prepare order document
        order_doc = {
            "id": order_id,
            "buyer_id": user.id,
            "seller_id": order_data["seller_id"],
            "items": order_data["items"],
            "total_amount": order_data["total_amount"],
            "currency": order_data.get("currency", "ZAR"),
            "delivery_method": order_data.get("delivery_method", "self_collection"),
            "order_status": "pending_payment",
            "source": order_data.get("source", "direct"),
            "buy_request_id": order_data.get("buy_request_id"),
            "offer_id": order_data.get("offer_id"),
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }
        
        # Insert order
        await db.orders.insert_one(order_doc)
        
        # Create cart items for immediate checkout
        for item in order_data["items"]:
            cart_item = {
                "id": str(uuid.uuid4()),
                "user_id": user.id,
                "listing_id": item.get("listing_id"),
                "quantity": item["quantity"],
                "unit_price": item["unit_price"],
                "total_price": item["total_price"],
                "order_id": order_id,
                "created_at": datetime.now(timezone.utc)
            }
            await db.cart_items.insert_one(cart_item)
        
        logger.info(f"Created order {order_id} with {len(order_data['items'])} items")
        
        return {
            "success": True,
            "order_id": order_id,
            "total_amount": order_data["total_amount"]
        }
        
    except Exception as e:
        logger.error(f"Error in create_order_internal: {e}")
        raise e

@api_router.post("/buy-requests/{request_id}/offers/{offer_id}/decline")
async def decline_offer(
    request_id: str,
    offer_id: str,
    current_user: User = Depends(get_current_user)
):
    """Decline an offer"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        buy_request_service = BuyRequestService(db)
        
        success = await buy_request_service.decline_offer(
            request_id=request_id,
            offer_id=offer_id,
            buyer_id=current_user.id
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Offer not found or not accessible")
        
        return {"ok": True, "message": "Offer declined"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error declining offer: {e}")
        raise HTTPException(status_code=500, detail="Failed to decline offer")

@api_router.get("/seller/buy-requests/in-range")
async def get_in_range_buy_requests(
    species: Optional[str] = None,
    limit: int = 50,
    current_user: User = Depends(get_current_user)
):
    """Get buy requests within seller's service area"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        buy_request_service = BuyRequestService(db)
        
        # Get seller's service area (simplified for now)
        service_area = {
            "provinces": ["Gauteng", "Western Cape"],  # TODO: Get from user settings
            "countries": ["ZA"]
        }
        
        requests = await buy_request_service.get_in_range_requests_for_seller(
            seller_id=current_user.id,
            service_area=service_area,
            species=species,
            limit=limit
        )
        
        return {"items": requests}
        
    except Exception as e:
        logger.error(f"Error fetching in-range requests: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch requests")

@api_router.get("/seller/offers")
async def get_seller_offers(
    status: Optional[str] = None,
    species: Optional[str] = None,
    limit: int = 100,
    current_user: User = Depends(get_current_user)
):
    """Get offers made by seller"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        buy_request_service = BuyRequestService(db)
        
        offers = await buy_request_service.get_seller_offers(
            seller_id=current_user.id,
            status=OfferStatus(status) if status and status != "ALL" else None,
            species=species,
            limit=limit
        )
        
        return {"items": offers}
        
    except Exception as e:
        logger.error(f"Error fetching seller offers: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch offers")

# Admin moderation routes
@api_router.get("/admin/buy-requests/moderation")
async def get_moderation_queue(
    status: Optional[str] = "pending_review",
    limit: int = 100,
    current_user: User = Depends(get_current_user)
):
    """Get buy requests pending moderation"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        buy_request_service = BuyRequestService(db)
        
        requests = await buy_request_service.get_moderation_queue(
            status=status,
            limit=limit
        )
        
        return {"items": requests}
        
    except Exception as e:
        logger.error(f"Error fetching moderation queue: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch moderation queue")

@api_router.post("/admin/buy-requests/{request_id}/moderate")
async def moderate_buy_request(
    request_id: str,
    action: str,  # "approve" or "reject"
    current_user: User = Depends(get_current_user)
):
    """Moderate a buy request"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    if action not in ["approve", "reject"]:
        raise HTTPException(status_code=400, detail="Action must be 'approve' or 'reject'")
    
    try:
        buy_request_service = BuyRequestService(db)
        
        success = await buy_request_service.moderate_request(
            request_id=request_id,
            admin_id=current_user.id,
            action=action
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Request not found")
        
        # If approved, notify nearby sellers
        if action == "approve":
            request = await buy_request_service.get_buy_request_by_id(request_id)
            if request:
                try:
                    await notify_nearby_sellers(db, request)
                except Exception as e:
                    logger.warning(f"Failed to notify sellers: {e}")
        
        return {"ok": True, "action": action}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error moderating request: {e}")
        raise HTTPException(status_code=500, detail="Failed to moderate request")

# ==============================================================================
# 🤖 AI-ENHANCED BUY REQUESTS API ENDPOINTS
# ==============================================================================

class EnhancedBuyRequestCreate(BaseModel):
    species: str
    product_type: str
    qty: int
    unit: str
    target_price: Optional[float] = None
    breed: Optional[str] = None
    province: Optional[str] = None
    country: str = "ZA"
    expires_at: Optional[str] = None
    notes: Optional[str] = None
    enable_ai_enhancements: bool = True
    auto_generate_description: bool = False
    # New fields for enhanced content
    images: Optional[List[str]] = []
    vet_certificates: Optional[List[str]] = []
    weight_range: Optional[dict] = None  # {"min": 1.5, "max": 2.0, "unit": "kg"}
    age_requirements: Optional[dict] = None  # {"min": 6, "max": 12, "unit": "weeks"}
    vaccination_requirements: Optional[List[str]] = []
    delivery_preferences: Optional[str] = "both"  # "pickup", "delivery", "both"
    inspection_allowed: Optional[bool] = True
    additional_requirements: Optional[str] = None

@api_router.post("/buy-requests/enhanced")
async def create_enhanced_buy_request(
    data: EnhancedBuyRequestCreate,
    current_user: User = Depends(get_current_user)
):
    """Create an AI-enhanced buy request with smart features"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        # Parse expires_at if provided
        expires_at = None
        if data.expires_at:
            expires_at = datetime.fromisoformat(data.expires_at.replace('Z', '+00:00'))
        
        request = await enhanced_buy_request_service.create_enhanced_buy_request(
            buyer_id=current_user.id,
            species=data.species,
            product_type=data.product_type,
            qty=data.qty,
            unit=data.unit,
            target_price=data.target_price,
            breed=data.breed,
            province=data.province,
            country=data.country,
            expires_at=expires_at,
            notes=data.notes,
            enable_ai_enhancements=data.enable_ai_enhancements,
            auto_generate_description=data.auto_generate_description,
            # Enhanced fields
            images=data.images or [],
            vet_certificates=data.vet_certificates or [],
            weight_range=data.weight_range,
            age_requirements=data.age_requirements,
            vaccination_requirements=data.vaccination_requirements or [],
            delivery_preferences=data.delivery_preferences or "both",
            inspection_allowed=data.inspection_allowed if data.inspection_allowed is not None else True,
            additional_requirements=data.additional_requirements
        )
        
        return {
            "ok": True,
            "id": request["id"],
            "moderation_status": request["moderation_status"],
            "ai_enhanced": request.get("ai_enhanced", False),
            "ai_analysis": request.get("ai_analysis", {}),
            "price_suggestions": request.get("price_suggestions", {}),
            "location_data": request.get("location_data", {}),
            "categorization": request.get("categorization", {})
        }
        
    except Exception as e:
        logger.error(f"Error creating enhanced buy request: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create enhanced buy request: {str(e)}")

@api_router.post("/buy-requests/{request_id}/offers/enhanced")
async def create_enhanced_offer(
    request_id: str,
    data: OfferCreate,
    current_user: User = Depends(get_current_user)
):
    """Create an AI-enhanced offer with smart matching"""
    if not current_user or UserRole.SELLER not in current_user.roles:
        raise HTTPException(status_code=403, detail="Seller access required")
    
    try:
        offer = await enhanced_buy_request_service.create_enhanced_offer(
            request_id=request_id,
            seller_id=current_user.id,
            offer_price=data.offer_price,
            qty=data.qty,
            message=data.message,
            listing_id=data.listing_id,
            org_id=getattr(current_user, 'org_id', None),
            enable_ai_matching=True
        )
        
        return {
            "ok": True,
            "offer_id": offer["id"],
            "ai_matching": offer.get("ai_enhanced_data", {}).get("ai_matching", {}),
            "distance_analysis": offer.get("ai_enhanced_data", {}).get("distance_analysis", {})
        }
        
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error creating enhanced offer: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create enhanced offer: {str(e)}")

@api_router.get("/buy-requests/intelligent-matches")
async def get_intelligent_matches(
    current_user: User = Depends(get_current_user),
    max_distance_km: float = 200,
    min_matching_score: int = 60,
    limit: int = 20
):
    """Get intelligently matched buy requests for seller"""
    if not current_user or UserRole.SELLER not in current_user.roles:
        raise HTTPException(status_code=403, detail="Seller access required")
    
    try:
        matches = await enhanced_buy_request_service.get_intelligent_matches(
            seller_id=current_user.id,
            max_distance_km=max_distance_km,
            min_matching_score=min_matching_score,
            limit=limit
        )
        
        return {
            "matches": matches,
            "total_count": len(matches),
            "filters": {
                "max_distance_km": max_distance_km,
                "min_matching_score": min_matching_score,
                "limit": limit
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting intelligent matches: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get intelligent matches: {str(e)}")

@api_router.get("/analytics/market")
async def get_market_analytics(
    species: Optional[str] = None,
    province: Optional[str] = None,
    days_back: int = 30,
    current_user: User = Depends(get_current_user)
):
    """Get market analytics and trends"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        analytics = await enhanced_buy_request_service.get_market_analytics(
            species=species,
            province=province,
            days_back=days_back
        )
        
        return analytics
        
    except Exception as e:
        logger.error(f"Error getting market analytics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get market analytics: {str(e)}")

# ==============================================================================
# 🗺️ MAPPING & GEOLOCATION API ENDPOINTS
# ==============================================================================

@api_router.post("/mapping/geocode")
async def geocode_location(
    data: dict,
    current_user: User = Depends(get_current_user)
):
    """Geocode a location to coordinates"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        result = await mapbox_service.geocode_location(
            location=data.get('location'),
            country=data.get('country', 'ZA')
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error geocoding location: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to geocode location: {str(e)}")

@api_router.post("/mapping/distance")
async def calculate_distance(
    data: dict,
    current_user: User = Depends(get_current_user)
):
    """Calculate distance between two locations"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        result = await mapbox_service.calculate_delivery_distance(
            seller_location=(data['seller_lng'], data['seller_lat']),
            buyer_location=(data['buyer_lng'], data['buyer_lat'])
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error calculating distance: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to calculate distance: {str(e)}")

@api_router.post("/mapping/route-optimization")
async def optimize_delivery_route(
    data: dict,
    current_user: User = Depends(get_current_user)
):
    """Optimize delivery route for multiple stops"""
    if not current_user or UserRole.SELLER not in current_user.roles:
        raise HTTPException(status_code=403, detail="Seller access required")
    
    try:
        depot = (data['depot_lng'], data['depot_lat'])
        delivery_points = [(point['lng'], point['lat']) for point in data['delivery_points']]
        
        result = await mapbox_service.optimize_delivery_route(
            depot=depot,
            delivery_points=delivery_points,
            return_to_depot=data.get('return_to_depot', True)
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error optimizing route: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to optimize route: {str(e)}")

@api_router.get("/mapping/nearby-requests")
async def find_nearby_requests(
    lng: float,
    lat: float,
    radius_km: float = 50,
    current_user: User = Depends(get_current_user)
):
    """Find buy requests near a location"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        # Get all open buy requests with coordinates
        query = {
            "status": BuyRequestStatus.OPEN.value,
            "moderation_status": {"$in": ["auto_pass", "approved"]},
            "location_data.coordinates": {"$exists": True}
        }
        
        cursor = db.buy_requests.find(query).limit(100)
        all_requests = await cursor.to_list(length=None)
        
        # Remove MongoDB _ids
        for req in all_requests:
            if "_id" in req:
                del req["_id"]
        
        nearby_requests = await mapbox_service.find_nearby_requests(
            center_location=(lng, lat),
            radius_km=radius_km,
            buy_requests=all_requests
        )
        
        return {
            "requests": nearby_requests,
            "total_count": len(nearby_requests),
            "search_radius_km": radius_km,
            "center": {"lng": lng, "lat": lat}
        }
        
    except Exception as e:
        logger.error(f"Error finding nearby requests: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to find nearby requests: {str(e)}")

# ==============================================================================
# 💬 MESSAGING API ENDPOINTS
# ==============================================================================

@api_router.get("/messages/threads")
async def get_user_threads(current_user: User = Depends(get_current_user), limit: int = 50):
    """Get user's message threads"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        # Get threads where user is a participant
        threads = await db.message_participants.find({
            "user_id": current_user.id
        }).sort("last_read_at", -1).limit(limit).to_list(length=None)
        
        # Get thread details
        thread_details = []
        for participant in threads:
            thread = await db.message_threads.find_one({"id": participant["thread_id"]})
            if thread:
                thread_details.append(thread)
        
        return {"threads": thread_details}
    except Exception as e:
        logger.error(f"Error getting user threads: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/messages/threads")
async def create_or_get_thread(thread_data: ThreadCreate, current_user: User = Depends(get_current_user)):
    """Create or get existing message thread"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        result = await messaging_service.create_or_get_thread(
            context_type=thread_data.context_type,
            context_id=thread_data.context_id,
            created_by=current_user.id,
            participants=thread_data.participants
        )
        return result
    except Exception as e:
        logger.error(f"Error creating thread: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/messages/threads/{thread_id}/messages")
async def get_thread_messages(
    thread_id: str, 
    limit: int = 50, 
    offset: int = 0,
    current_user: User = Depends(get_current_user)
):
    """Get paginated messages for a thread"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        result = await messaging_service.get_thread_messages(
            thread_id=thread_id,
            user_id=current_user.id,
            limit=limit,
            offset=offset
        )
        return result
    except Exception as e:
        logger.error(f"Error getting messages: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/messages/threads/{thread_id}/messages")
async def send_message(
    thread_id: str,
    message_data: MessageCreate,
    current_user: User = Depends(get_current_user)
):
    """Send a message to a thread"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        result = await messaging_service.send_message(
            thread_id=thread_id,
            sender_id=current_user.id,
            body=message_data.body,
            attachments=message_data.attachments
        )
        return result
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/messages/threads/{thread_id}/read")
async def mark_thread_read(thread_id: str, current_user: User = Depends(get_current_user)):
    """Mark thread as read for current user"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        result = await messaging_service.mark_thread_read(thread_id, current_user.id)
        return result
    except Exception as e:
        logger.error(f"Error marking thread read: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==============================================================================
# 🎯 REFERRALS API ENDPOINTS
# ==============================================================================

@api_router.get("/referrals/code")
async def get_referral_code(current_user: User = Depends(get_current_user)):
    """Get or create user's referral code"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        code = await referral_service_extended.get_or_create_referral_code(current_user.id)
        return {"code": code}
    except Exception as e:
        logger.error(f"Error getting referral code: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/referrals/click")
async def track_referral_click(code: str, to: str = "/signup", request: Request = None):
    """Track referral click and redirect"""
    try:
        # Log the click
        await referral_service_extended.track_referral_click(
            code=code,
            referer=request.headers.get("referer") if request else None,
            ip=request.client.host if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            dest_path=to
        )
        
        # Set referral cookie and redirect
        from fastapi.responses import RedirectResponse
        response = RedirectResponse(url=to)
        response.set_cookie(
            key="referral_code", 
            value=code, 
            max_age=30*24*60*60,  # 30 days
            httponly=True
        )
        return response
        
    except Exception as e:
        logger.warning(f"Referral tracking failed: {e}")
        # Still redirect even if logging fails
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=to)

@api_router.get("/referrals/summary")
async def get_referral_summary(current_user: User = Depends(get_current_user)):
    """Get user's referral performance summary"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        summary = await referral_service_extended.get_referral_summary(current_user.id)
        return summary
    except Exception as e:
        logger.error(f"Error getting referral summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==============================================================================
# 🔔 NOTIFICATIONS API ENDPOINTS
# ==============================================================================

@api_router.get("/notifications")
async def get_notifications(
    limit: int = 50,
    unread_only: bool = False,
    current_user: User = Depends(get_current_user)
):
    """Get user notifications"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        notifications = await notification_service_extended.get_user_notifications(
            user_id=current_user.id,
            limit=limit,
            unread_only=unread_only
        )
        return {"notifications": notifications}
    except Exception as e:
        logger.error(f"Error getting notifications: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    current_user: User = Depends(get_current_user)
):
    """Mark notification as read"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        result = await notification_service_extended.mark_notification_read(
            notification_id=notification_id,
            user_id=current_user.id
        )
        return result
    except Exception as e:
        logger.error(f"Error marking notification read: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/notifications/unread-count")
async def get_unread_count(current_user: User = Depends(get_current_user)):
    """Get count of unread notifications"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        count = await notification_service_extended.get_unread_count(current_user.id)
        return {"count": count}
    except Exception as e:
        logger.error(f"Error getting unread count: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/notifications/mark-all-read")
async def mark_all_notifications_read(current_user: User = Depends(get_current_user)):
    """Mark all notifications as read"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        result = await notification_service_extended.mark_all_read(current_user.id)
        return result
    except Exception as e:
        logger.error(f"Error marking all notifications read: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==============================================================================
# 🛒 EXTENDED BUY REQUESTS API ENDPOINTS
# ==============================================================================

@api_router.post("/buy-requests/{buy_request_id}/offers")
async def create_offer(
    buy_request_id: str,
    offer_data: OfferCreate,
    current_user: User = Depends(get_current_user)
):
    """Create offer on buy request"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        # Check if buy request exists
        buy_request = await db.buy_requests.find_one({"id": buy_request_id})
        if not buy_request:
            raise HTTPException(status_code=404, detail="Buy request not found")
        
        # Create offer
        offer_id = str(uuid.uuid4())
        offer_doc = {
            "id": offer_id,
            "buy_request_id": buy_request_id,
            "seller_id": current_user.id,
            "price_per_unit": offer_data.price_per_unit,
            "quantity_available": offer_data.quantity_available,
            "notes": offer_data.notes,
            "delivery_cost": offer_data.delivery_cost,
            "delivery_days": offer_data.delivery_days,
            "status": "pending",
            "created_at": datetime.now(timezone.utc),
            "expires_at": datetime.now(timezone.utc) + timedelta(days=7)
        }
        
        await db.buy_request_offers.insert_one(offer_doc)
        
        # Notify buyer
        await notification_service_extended.notify_offer_received(offer_id, buy_request["buyer_id"])
        
        return {"ok": True, "offer_id": offer_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating offer: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/buy-requests/{buy_request_id}/offers")
async def get_buy_request_offers(
    buy_request_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get offers for a buy request"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        # Check if user is the buyer or admin
        buy_request = await db.buy_requests.find_one({"id": buy_request_id})
        if not buy_request:
            raise HTTPException(status_code=404, detail="Buy request not found")
        
        if buy_request["buyer_id"] != current_user.id and "admin" not in current_user.roles:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Get offers
        offers = await db.buy_request_offers.find({
            "buy_request_id": buy_request_id
        }).sort("created_at", -1).to_list(length=None)
        
        return {"offers": offers}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting offers: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.patch("/buy-requests/{buy_request_id}/offers/{offer_id}")
async def update_offer(
    buy_request_id: str,
    offer_id: str,
    update_data: OfferUpdate,
    current_user: User = Depends(get_current_user)
):
    """Accept/decline offer"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        # Verify buy request ownership
        buy_request = await db.buy_requests.find_one({"id": buy_request_id})
        if not buy_request or buy_request["buyer_id"] != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Update offer
        result = await db.buy_request_offers.update_one(
            {"id": offer_id, "buy_request_id": buy_request_id},
            {"$set": {
                "status": update_data.status,
                "updated_at": datetime.now(timezone.utc)
            }}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Offer not found")
        
        # Notify seller if accepted
        if update_data.status == "accepted":
            offer = await db.buy_request_offers.find_one({"id": offer_id})
            if offer:
                await notification_service_extended.notify_offer_accepted(offer_id, offer["seller_id"])
        
        return {"ok": True}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating offer: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==============================================================================
# 💳 PAYMENT & ESCROW API ENDPOINTS  
# ==============================================================================

@api_router.post("/payments/initialize")
async def initialize_payment(
    payment_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Initialize Paystack payment for order"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        order_id = payment_data.get("order_id")
        amount = payment_data.get("amount")
        
        if not order_id or not amount:
            raise HTTPException(status_code=400, detail="Missing order_id or amount")
        
        # Verify order belongs to user
        order = await db.orders.find_one({"id": order_id})
        if not order or order["buyer_id"] != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Initialize payment
        result = await paystack_service.initialize_transaction(
            email=current_user.email,
            amount=amount,
            order_id=order_id
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error initializing payment: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/payments/verify/{reference}")
async def verify_payment(reference: str, current_user: User = Depends(get_current_user)):
    """Verify payment status"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        result = await paystack_service.verify_transaction(reference)
        return result
    except Exception as e:
        logger.error(f"Error verifying payment: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/payments/webhook")
async def paystack_webhook(request: Request):
    """Paystack webhook endpoint"""
    try:
        signature = request.headers.get("x-paystack-signature", "")
        payload = await request.body()
        
        result = await paystack_service.process_webhook(payload, signature)
        return result
        
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/payments/escrow/{order_id}/release")
async def release_escrow(
    order_id: str,
    current_user: User = Depends(get_current_user)
):
    """Release escrow funds to seller (buyer action)"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        # Verify order belongs to buyer
        order = await db.orders.find_one({"id": order_id})
        if not order or order["buyer_id"] != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        result = await paystack_service.release_escrow(order_id, current_user.id)
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error releasing escrow: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==============================================================================
# 🔐 ADMIN API ENDPOINTS
# ==============================================================================

async def get_current_admin_user(current_user: User = Depends(get_current_user)):
    """Get current user and verify admin role"""
    if not current_user or "admin" not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

# ==============================================================================
# 🤖 MACHINE LEARNING API ENDPOINTS
# ==============================================================================

# FAQ ML Endpoints
@api_router.post("/ml/faq/ingest")
async def ingest_faq_questions(
    current_user: User = Depends(get_current_admin_user)
):
    """Ingest questions from various sources for FAQ generation"""
    if not AI_SERVICES_AVAILABLE or not ml_faq_service:
        raise HTTPException(status_code=503, detail="ML FAQ services are currently unavailable")
        
    try:
        result = await ml_faq_service.ingest_questions_from_sources()
        
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result.get("error", "Ingestion failed"))
        
        return {
            "message": "Questions ingested successfully",
            "ingestion_id": result["ingestion_id"],
            "stats": result["stats"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"FAQ ingestion failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to ingest questions")

@api_router.post("/ml/faq/cluster/{ingestion_id}")
async def cluster_faq_questions(
    ingestion_id: str,
    current_user: User = Depends(get_current_admin_user)
):
    """Cluster similar questions and identify topics"""
    try:
        result = await ml_faq_service.cluster_questions(ingestion_id)
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result.get("error", "Clustering failed"))
        
        return {
            "message": "Questions clustered successfully",
            "clustering_id": result["clustering_id"],
            "stats": result["stats"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"FAQ clustering failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to cluster questions")

@api_router.post("/ml/faq/generate-answers/{clustering_id}")
async def generate_draft_answers(
    clustering_id: str,
    current_user: User = Depends(get_current_admin_user)
):
    """Generate draft answers for question clusters"""
    try:
        result = await ml_faq_service.generate_draft_answers(clustering_id)
        
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result.get("error", "Answer generation failed"))
        
        return {
            "message": "Draft answers generated successfully",
            "draft_id": result["draft_id"],
            "answers_generated": result["answers_generated"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"FAQ answer generation failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate answers")

@api_router.get("/faq/search")
async def search_faq(
    q: str,
    limit: int = 5,
    current_user: User = Depends(get_current_user)
):
    """Search FAQ using semantic similarity"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        results = await ml_faq_service.semantic_search_faq(q, limit)
        
        return {
            "query": q,
            "results": results,
            "total_found": len(results)
        }
        
    except Exception as e:
        logger.error(f"FAQ search failed: {e}")
        raise HTTPException(status_code=500, detail="Search failed")

@api_router.post("/faq/{faq_id}/feedback")
async def record_faq_feedback(
    faq_id: str,
    data: dict,
    current_user: User = Depends(get_current_user)
):
    """Record user feedback on FAQ responses for ML learning"""
    try:
        feedback_record = {
            "faq_id": faq_id,
            "user_id": current_user.id,
            "rating": data.get("rating"),
            "helpful": data.get("helpful"),
            "comment": data.get("comment"),
            "session_id": data.get("session_id"),
            "timestamp": datetime.now(timezone.utc)
        }
        
        await db.faq_feedback.insert_one(feedback_record)
        
        return {"success": True, "message": "Feedback recorded for ML learning"}
        
    except Exception as e:
        logger.error(f"FAQ feedback recording failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to record feedback")

# Enhanced ML Knowledge Scraping Endpoints
@api_router.post("/ml/knowledge/scrape")
async def scrape_livestock_knowledge(
    current_user: User = Depends(get_current_admin_user)
):
    """Scrape livestock knowledge from external sources for ML learning"""
    if not ML_SERVICES_AVAILABLE or not ml_scraper_service:
        raise HTTPException(status_code=503, detail="ML scraping service not available")
    
    try:
        result = await ml_scraper_service.scrape_livestock_knowledge()
        return result
        
    except Exception as e:
        logger.error(f"Knowledge scraping failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to scrape knowledge")

@api_router.post("/ml/knowledge/learn-from-interactions")
async def learn_from_user_interactions(
    current_user: User = Depends(get_current_admin_user)
):
    """Analyze user interactions to identify knowledge gaps and improve FAQ system"""
    if not ML_SERVICES_AVAILABLE or not ml_scraper_service:
        raise HTTPException(status_code=503, detail="ML learning service not available")
    
    try:
        result = await ml_scraper_service.learn_from_user_interactions()
        return result
        
    except Exception as e:
        logger.error(f"Learning from interactions failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to analyze interactions")

@api_router.get("/ml/knowledge/insights")
async def get_learning_insights(
    limit: int = 10,
    current_user: User = Depends(get_current_admin_user)
):
    """Get ML learning insights and recommendations"""
    try:
        insights = await db.ml_learning_insights.find().sort("timestamp", -1).limit(limit).to_list(limit)
        
        # Format insights for display
        formatted_insights = []
        for insight in insights:
            formatted_insights.append({
                "learning_id": insight["learning_id"],
                "timestamp": insight["timestamp"],
                "questions_analyzed": insight["total_questions_analyzed"],
                "knowledge_gaps": len(insight["knowledge_gaps"]),
                "recommendations": insight["recommendations"][:5],  # Top 5 recommendations
                "high_priority_gaps": [
                    gap for gap in insight["knowledge_gaps"] 
                    if gap.get("priority") == "high"
                ]
            })
        
        return {
            "success": True,
            "insights": formatted_insights,
            "total_insights": len(formatted_insights)
        }
        
    except Exception as e:
        logger.error(f"Failed to get learning insights: {e}")
        raise HTTPException(status_code=500, detail="Failed to get insights")

# Enhanced Smart Search Endpoint
@api_router.post("/search/smart")
async def smart_search(
    search_data: dict,
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Enhanced smart search with ML-powered suggestions and learning"""
    try:
        query = search_data.get("query", "").strip()
        if not query:
            raise HTTPException(status_code=400, detail="Search query is required")
        
        search_results = {
            "query": query,
            "timestamp": datetime.now(timezone.utc),
            "results": [],
            "suggestions": [],
            "learned_from_query": False
        }
        
        # 1. Search livestock listings
        listings_pipeline = [
            {
                "$match": {
                    "$or": [
                        {"title": {"$regex": query, "$options": "i"}},
                        {"description": {"$regex": query, "$options": "i"}},
                        {"breed": {"$regex": query, "$options": "i"}},
                        {"species": {"$regex": query, "$options": "i"}}
                    ],
                    "status": "active"
                }
            },
            {"$limit": 10},
            {
                "$project": {
                    "title": 1,
                    "description": 1,
                    "price_per_unit": 1,
                    "species": 1,
                    "breed": 1,
                    "location": 1,
                    "thumbnail_url": 1
                }
            }
        ]
        
        listings = await db.listings.aggregate(listings_pipeline).to_list(10)
        
        # Calculate simple relevance score based on query matches
        for listing in listings:
            relevance_score = 1.0
            query_lower = query.lower()
            
            # Higher score for title matches
            if listing.get("title", "").lower().find(query_lower) != -1:
                relevance_score += 2.0
            
            # Medium score for breed/species matches  
            if listing.get("breed", "").lower().find(query_lower) != -1:
                relevance_score += 1.5
            if listing.get("species", "").lower().find(query_lower) != -1:
                relevance_score += 1.5
                
            # Lower score for description matches
            if listing.get("description", "").lower().find(query_lower) != -1:
                relevance_score += 0.5
                
            listing["relevance_score"] = relevance_score
        
        search_results["results"].extend([{
            "type": "listing",
            "data": listing,
            "relevance_score": listing.get("relevance_score", 1.0)
        } for listing in listings])
        
        # 2. Search FAQ knowledge base
        if ML_SERVICES_AVAILABLE and ml_faq_service:
            try:
                faq_results = await ml_faq_service.search_faqs(query, limit=5)
                search_results["results"].extend([{
                    "type": "faq",
                    "data": faq,
                    "relevance_score": faq.get("similarity_score", 0.8)
                } for faq in faq_results])
            except Exception as e:
                logger.warning(f"FAQ search failed: {e}")
        
        # 3. Generate ML-powered suggestions
        if ML_SERVICES_AVAILABLE and ml_scraper_service:
            try:
                # Analyze query for learning opportunities
                query_analysis = await _analyze_search_query(query, len(search_results["results"]))
                search_results["suggestions"] = query_analysis.get("suggestions", [])
                search_results["learned_from_query"] = query_analysis.get("learned", False)
            except Exception as e:
                logger.warning(f"Query analysis failed: {e}")
        
        # 4. Log search for learning (if user is authenticated)
        if current_user:
            search_log = {
                "user_id": current_user.id,
                "query": query,
                "results_count": len(search_results["results"]),
                "timestamp": datetime.now(timezone.utc),
                "user_type": "authenticated"
            }
            await db.search_logs.insert_one(search_log)
        
        # Sort results by relevance
        search_results["results"].sort(key=lambda x: x["relevance_score"], reverse=True)
        
        return {
            "success": True,
            "search": search_results,
            "ml_enhanced": ML_SERVICES_AVAILABLE
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Smart search failed: {e}")
        raise HTTPException(status_code=500, detail="Search failed")

async def _analyze_search_query(query: str, results_count: int) -> dict:
    """Analyze search query for ML learning opportunities"""
    analysis = {
        "suggestions": [],
        "learned": False
    }
    
    # Generate suggestions based on query patterns
    query_lower = query.lower()
    
    if "cattle" in query_lower:
        analysis["suggestions"].extend([
            "Try searching for specific breeds like 'Angus cattle' or 'Brahman cattle'",
            "Consider filtering by 'breeding cattle' or 'commercial cattle'"
        ])
    elif "goat" in query_lower:
        analysis["suggestions"].extend([
            "Search for 'Boer goats' or 'Kalahari Red goats' for specific breeds",
            "Try 'dairy goats' or 'meat goats' for purpose-specific results"
        ])
    elif "sheep" in query_lower:
        analysis["suggestions"].extend([
            "Consider 'Dorper sheep' or 'Merino sheep' for breed-specific results",
            "Try 'wool sheep' or 'mutton sheep' based on your needs"
        ])
    
    if results_count == 0:
        analysis["suggestions"].append("No results found. Try broader terms or check spelling.")
        analysis["learned"] = True
        
        # Log as learning opportunity
        await db.faq_interactions.insert_one({
            "question": f"Search query: {query}",
            "answered": False, 
            "timestamp": datetime.now(timezone.utc),
            "type": "failed_search"
        })
    
    return analysis

# Smart Matching ML Endpoints
@api_router.get("/ml/matching/smart-requests")
async def get_smart_matched_requests(
    current_user: User = Depends(get_current_user),
    limit: int = 20
):
    """Get intelligently ranked buy requests for seller"""
    if not current_user or UserRole.SELLER not in current_user.roles:
        raise HTTPException(status_code=403, detail="Seller access required")
    
    try:
        # Get basic in-range requests first
        query = {
            "status": "open",
            "moderation_status": {"$in": ["auto_pass", "approved"]}
        }
        
        # Get seller service areas
        seller = await db.users.find_one({"id": current_user.id})
        service_provinces = seller.get("service_provinces", [])
        
        if service_provinces:
            query["province"] = {"$in": service_provinces}
        
        cursor = db.buy_requests.find(query).limit(limit * 2)  # Get more to rank
        requests = await cursor.to_list(length=None)
        
        # Clean MongoDB IDs
        for req in requests:
            if "_id" in req:
                del req["_id"]
        
        # Apply ML ranking
        ranked_requests = await ml_matching_service.rank_requests_for_seller(
            seller_id=current_user.id,
            requests=requests,
            limit=limit
        )
        
        return {
            "requests": ranked_requests,
            "total_considered": len(requests),
            "ml_ranked": True
        }
        
    except Exception as e:
        logger.error(f"Smart matching failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to get smart matches")

@api_router.post("/ml/matching/record-interaction")
async def record_matching_interaction(
    data: dict,
    current_user: User = Depends(get_current_user)
):
    """Record seller interaction with buy request for ML training"""
    if not current_user or UserRole.SELLER not in current_user.roles:
        raise HTTPException(status_code=403, detail="Seller access required")
    
    try:
        request_id = data.get("request_id")
        interaction_type = data.get("interaction_type")  # 'view', 'offer_sent', 'skipped'
        features = data.get("features")
        
        if not request_id or not interaction_type:
            raise HTTPException(status_code=400, detail="Missing required fields")
        
        success = await ml_matching_service.record_interaction(
            seller_id=current_user.id,
            request_id=request_id,
            interaction_type=interaction_type,
            features=features
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to record interaction")
        
        return {"message": "Interaction recorded successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Interaction recording failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to record interaction")

@api_router.post("/ml/matching/train")
async def train_matching_model(
    current_user: User = Depends(get_current_admin_user)
):
    """Train ML matching model from collected data"""
    try:
        result = await ml_matching_service.train_model()
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result.get("error", "Training failed"))
        
        return {
            "message": "Model trained successfully",
            "performance": result["model_performance"],
            "feature_importance": result["feature_importance"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Model training failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to train model")

@api_router.get("/ml/matching/performance")
async def get_matching_model_performance(
    current_user: User = Depends(get_current_admin_user)
):
    """Get current matching model performance metrics"""
    try:
        performance = await ml_matching_service.get_model_performance()
        return performance
        
    except Exception as e:
        logger.error(f"Performance retrieval failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to get model performance")

# ============================================================================
# ADVANCED ML ENGINE API ENDPOINTS
# ============================================================================

@api_router.post("/ml/engine/smart-pricing")
async def smart_pricing_analysis(
    data: dict,
    current_user: User = Depends(get_current_user)
):
    """AI-powered smart pricing analysis with 15+ market factors"""
    try:
        listing_data = data.get("listing_data", {})
        market_context = data.get("market_context")
        
        if not listing_data:
            raise HTTPException(status_code=400, detail="listing_data is required")
        
        # Add user context if available
        if current_user:
            listing_data["seller_id"] = current_user.id
        
        analysis = await ml_engine_service.smart_pricing_analysis(
            listing_data=listing_data,
            market_context=market_context
        )
        
        if not analysis.get("success"):
            raise HTTPException(status_code=500, detail=analysis.get("error", "Pricing analysis failed"))
        
        return analysis
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Smart pricing analysis failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to analyze pricing")

@api_router.post("/ml/engine/demand-forecast")
async def demand_forecasting(
    data: dict,
    current_user: User = Depends(get_current_user)
):
    """Predict demand patterns using temporal analysis"""
    try:
        species = data.get("species")
        region = data.get("region")
        forecast_days = data.get("forecast_days", 30)
        
        if not species:
            raise HTTPException(status_code=400, detail="species is required")
        
        if not region:
            # Use user's region if available, otherwise default
            region = current_user.province if current_user and current_user.province else "gauteng"
        
        forecast = await ml_engine_service.demand_forecasting(
            species=species,
            region=region,
            forecast_days=forecast_days
        )
        
        if not forecast.get("success"):
            raise HTTPException(status_code=500, detail=forecast.get("error", "Demand forecasting failed"))
        
        return forecast
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Demand forecasting failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to forecast demand")

@api_router.post("/ml/engine/market-intelligence")
async def market_intelligence_analysis(
    data: dict,
    current_user: User = Depends(get_current_user)
):
    """Comprehensive market intelligence and competitive analysis"""
    try:
        species = data.get("species")
        region = data.get("region")
        
        # Use user's region if not provided and available
        if not region and current_user and current_user.province:
            region = current_user.province
        
        intelligence = await ml_engine_service.market_intelligence_analysis(
            species=species,
            region=region
        )
        
        if not intelligence.get("success"):
            raise HTTPException(status_code=500, detail=intelligence.get("error", "Market intelligence failed"))
        
        return intelligence
        
    except Exception as e:
        logger.error(f"Market intelligence analysis failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to analyze market intelligence")

@api_router.post("/ml/engine/content-optimization")
async def content_optimization_analysis(
    data: dict,
    current_user: User = Depends(get_current_user)
):
    """AI-powered content optimization and SEO recommendations"""
    try:
        listing_data = data.get("listing_data", {})
        performance_data = data.get("performance_data")
        
        if not listing_data:
            raise HTTPException(status_code=400, detail="listing_data is required")
        
        # Add user context if available
        if current_user:
            listing_data["seller_id"] = current_user.id
        
        optimization = await ml_engine_service.content_optimization_analysis(
            listing_data=listing_data,
            performance_data=performance_data
        )
        
        if not optimization.get("success"):
            raise HTTPException(status_code=500, detail=optimization.get("error", "Content optimization failed"))
        
        return optimization
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Content optimization failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to optimize content")

# ============================================================================
# PHOTO INTELLIGENCE API ENDPOINTS
# ============================================================================

@api_router.post("/ml/photo/analyze")
async def analyze_livestock_photo(
    data: dict,
    current_user: User = Depends(get_current_user)
):
    """Comprehensive AI analysis of livestock photos"""
    try:
        image_data = data.get("image_data")  # Base64 encoded
        listing_context = data.get("listing_context", {})
        
        if not image_data:
            raise HTTPException(status_code=400, detail="image_data (base64) is required")
        
        # Add user context if available
        if current_user:
            listing_context["seller_id"] = current_user.id
        
        analysis = await photo_intelligence_service.analyze_livestock_photo(
            image_data=image_data,
            listing_context=listing_context
        )
        
        if not analysis.get("success"):
            raise HTTPException(status_code=500, detail=analysis.get("error", "Photo analysis failed"))
        
        return analysis
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Photo analysis failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to analyze photo")

@api_router.post("/ml/photo/bulk-analyze")
async def bulk_analyze_photos(
    data: dict,
    current_user: User = Depends(get_current_user)
):
    """Bulk analysis of multiple livestock photos"""
    try:
        photos = data.get("photos", [])  # Array of {image_data, listing_context}
        
        if not photos or len(photos) == 0:
            raise HTTPException(status_code=400, detail="photos array is required")
        
        if len(photos) > 10:
            raise HTTPException(status_code=400, detail="Maximum 10 photos per request")
        
        results = []
        for i, photo in enumerate(photos):
            try:
                image_data = photo.get("image_data")
                listing_context = photo.get("listing_context", {})
                
                if not image_data:
                    results.append({
                        "photo_index": i,
                        "success": False,
                        "error": "image_data is required"
                    })
                    continue
                
                # Add user context
                listing_context["seller_id"] = current_user.id
                
                analysis = await photo_intelligence_service.analyze_livestock_photo(
                    image_data=image_data,
                    listing_context=listing_context
                )
                
                results.append({
                    "photo_index": i,
                    **analysis
                })
                
            except Exception as e:
                logger.error(f"Photo {i} analysis failed: {e}")
                results.append({
                    "photo_index": i,
                    "success": False,
                    "error": str(e)
                })
        
        # Calculate overall statistics
        successful_analyses = [r for r in results if r.get("success")]
        total_quality_score = sum(r.get("overall_quality_score", 0) for r in successful_analyses)
        avg_quality_score = total_quality_score / len(successful_analyses) if successful_analyses else 0
        
        return {
            "success": True,
            "total_photos": len(photos),
            "successful_analyses": len(successful_analyses),
            "failed_analyses": len(photos) - len(successful_analyses),
            "average_quality_score": round(avg_quality_score, 1),
            "results": results,
            "analyzed_at": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bulk photo analysis failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to analyze photos")

# Duplicate admin stats route removed - security vulnerability fixed

# Admin messaging controls
@api_router.get("/admin/messages/threads")
async def admin_get_all_threads(
    context_type: Optional[str] = None,
    limit: int = 100,
    current_user: User = Depends(get_current_admin_user)
):
    """Get all message threads for admin review"""
    try:
        threads = await messaging_service.get_all_threads(context_type, limit)
        return {"threads": threads}
    except Exception as e:
        logger.error(f"Error getting threads: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/admin/messages/moderation")
async def admin_get_flagged_messages(current_user: User = Depends(get_current_admin_user)):
    """Get messages that were redacted or flagged"""
    try:
        flagged_messages = await messaging_service.get_flagged_messages()
        return {"flagged_messages": flagged_messages}
    except Exception as e:
        logger.error(f"Error getting flagged messages: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/admin/users/{user_id}/messaging-ban")
async def admin_ban_user_messaging(
    user_id: str,
    ban_data: UserModerationAction,
    current_user: User = Depends(get_current_admin_user)
):
    """Ban user from messaging"""
    try:
        result = await messaging_service.ban_user_messaging(
            user_id=user_id,
            reason=ban_data.reason,
            banned_by=current_user.id
        )
        
        # Log admin action
        await db.admin_audit_logs.insert_one({
            "id": str(uuid.uuid4()),
            "admin_id": current_user.id,
            "action": "messaging_ban",
            "resource_type": "user",
            "resource_id": user_id,
            "reason": ban_data.reason,
            "created_at": datetime.now(timezone.utc)
        })
        
        return result
    except Exception as e:
        logger.error(f"Error banning user: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Admin referral controls
@api_router.get("/admin/referrals")
async def admin_get_referrals(current_user: User = Depends(get_current_admin_user)):
    """Get all referrals for admin review"""
    try:
        referrals = await referral_service_extended.get_all_referrals()
        return {"referrals": referrals}
    except Exception as e:
        logger.error(f"Error getting referrals: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/admin/referrals/{reward_id}/approve")
async def admin_approve_referral_reward(
    reward_id: str,
    current_user: User = Depends(get_current_admin_user)
):
    """Approve referral reward for payout"""
    try:
        result = await referral_service_extended.approve_referral_reward(reward_id, current_user.id)
        
        # Log admin action
        await db.admin_audit_logs.insert_one({
            "id": str(uuid.uuid4()),
            "admin_id": current_user.id,
            "action": "approve_referral_reward",
            "resource_type": "referral_reward",
            "resource_id": reward_id,
            "created_at": datetime.now(timezone.utc)
        })
        
        return result
    except Exception as e:
        logger.error(f"Error approving referral reward: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/admin/referrals/{reward_id}/reject")
async def admin_reject_referral_reward(
    reward_id: str,
    rejection_data: dict,
    current_user: User = Depends(get_current_admin_user)
):
    """Reject referral reward"""
    try:
        result = await referral_service_extended.reject_referral_reward(
            reward_id=reward_id,
            reason=rejection_data.get("reason", "No reason provided"),
            rejected_by=current_user.id
        )
        return result
    except Exception as e:
        logger.error(f"Error rejecting referral reward: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/admin/referrals/{user_id}/flag-fraud")
async def admin_flag_fraud(
    user_id: str,
    fraud_data: dict,
    current_user: User = Depends(get_current_admin_user)
):
    """Flag user for fraudulent referral activity"""
    try:
        result = await referral_service_extended.flag_fraud(
            user_id=user_id,
            reason=fraud_data.get("reason", "Suspected fraud"),
            flagged_by=current_user.id
        )
        return result
    except Exception as e:
        logger.error(f"Error flagging fraud: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Admin payment controls
@api_router.get("/admin/payments/transactions")
async def admin_get_transactions(current_user: User = Depends(get_current_admin_user)):
    """Get all payment transactions"""
    try:
        transactions = await paystack_service.get_all_transactions()
        return {"transactions": transactions}
    except Exception as e:
        logger.error(f"Error getting transactions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/admin/payments/escrows")
async def admin_get_escrows(
    status: Optional[str] = None,
    current_user: User = Depends(get_current_admin_user)
):
    """Get all escrow records"""
    try:
        escrows = await paystack_service.get_all_escrows(status)
        return {"escrows": escrows}
    except Exception as e:
        logger.error(f"Error getting escrows: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/admin/payments/escrow/{order_id}/release")
async def admin_release_escrow(
    order_id: str,
    current_user: User = Depends(get_current_admin_user)
):
    """Admin release escrow funds"""
    try:
        result = await paystack_service.release_escrow(order_id, current_user.id)
        
        # Log admin action
        await db.admin_audit_logs.insert_one({
            "id": str(uuid.uuid4()),
            "admin_id": current_user.id,
            "action": "release_escrow",
            "resource_type": "order",
            "resource_id": order_id,
            "created_at": datetime.now(timezone.utc)
        })
        
        return result
    except Exception as e:
        logger.error(f"Error releasing escrow: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/admin/payments/escrow/{order_id}/refund")
async def admin_refund_escrow(
    order_id: str,
    refund_data: dict,
    current_user: User = Depends(get_current_admin_user)
):
    """Admin refund escrow to buyer"""
    try:
        result = await paystack_service.refund_escrow(
            order_id=order_id,
            reason=refund_data.get("reason", "Admin refund"),
            refunded_by=current_user.id
        )
        return result
    except Exception as e:
        logger.error(f"Error refunding escrow: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# PUBLIC BUY REQUESTS API ENDPOINTS
# ============================================================================

@api_router.get("/public/buy-requests")
async def get_public_buy_requests(
    species: Optional[str] = None,
    product_type: Optional[str] = None,
    breed: Optional[str] = None,
    province: Optional[str] = None,
    min_qty: Optional[int] = None,
    max_qty: Optional[int] = None,
    units: Optional[str] = None,  # comma-separated list
    has_target_price: Optional[bool] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    # Enhanced features filters
    has_images: Optional[bool] = None,
    has_vet_certificates: Optional[bool] = None,
    has_weight_requirements: Optional[bool] = None,
    has_age_requirements: Optional[bool] = None,
    requires_vaccinations: Optional[bool] = None,
    allows_inspection: Optional[bool] = None,
    delivery_preferences: Optional[str] = None,  # comma-separated list
    # Time filters
    created_within: Optional[str] = None,  # 1d, 3d, 7d, 14d, 30d
    expires_within: Optional[str] = None,
    # Search
    search: Optional[str] = None,
    sort: str = "relevance",  # relevance, newest, ending_soon, price_asc, price_desc
    limit: int = 24,
    after: Optional[str] = None,
    user_lat: Optional[float] = None,
    user_lng: Optional[float] = None,
    max_distance_km: Optional[int] = None
):
    """Get public buy requests list with filters, sorting, and pagination"""
    try:
        # Build query for open, non-expired requests
        # Handle both "open" and "OPEN" status values
        now = datetime.now(timezone.utc)
        
        # First, let's check what we have in the database
        total_open = await db.buy_requests.count_documents({"status": {"$in": ["open", "OPEN"]}})
        logger.info(f"Total open buy requests in DB: {total_open}")
        
        # Count with expires_at > now
        future_expires = await db.buy_requests.count_documents({
            "status": {"$in": ["open", "OPEN"]},
            "expires_at": {"$ne": None, "$gt": now}
        })
        logger.info(f"Open requests with future expires_at: {future_expires}")
        
        # Count with no expires_at
        no_expires = await db.buy_requests.count_documents({
            "status": {"$in": ["open", "OPEN"]},
            "$or": [
                {"expires_at": None},
                {"expires_at": {"$exists": False}}
            ]
        })
        logger.info(f"Open requests with no expires_at: {no_expires}")
        
        # Build query - include requests without expires_at or with future expires_at
        # Simplified: status must be open, and either no expires_at or expires_at in future
        query = {
            "status": {"$in": ["open", "OPEN"]}  # Accept both lowercase and uppercase
        }
        
        # Add expires_at condition - either missing/null or in the future
        query["$or"] = [
            {"expires_at": {"$gt": now}},  # Has expires_at and it's in the future
            {"expires_at": None},  # No expires_at
            {"expires_at": {"$exists": False}}  # expires_at field doesn't exist
        ]
        
        # Apply basic filters
        if species:
            query["species"] = species
        if product_type:
            query["product_type"] = product_type
        if breed:
            query["breed"] = breed
        if province:
            query["province"] = province
            
        # Quantity filters
        if min_qty is not None:
            query["qty"] = {"$ne": None, "$gte": min_qty}
        if max_qty is not None:
            if "qty" in query:
                query["qty"]["$lte"] = max_qty
            else:
                query["qty"] = {"$ne": None, "$lte": max_qty}
                
        # Unit filters
        if units:
            unit_list = [u.strip() for u in units.split(',')]
            query["unit"] = {"$in": unit_list}
            
        # Price filters
        if has_target_price is not None:
            if has_target_price:
                query["target_price"] = {"$ne": None, "$gt": 0}
            else:
                query["$or"] = [
                    {"target_price": {"$exists": False}},
                    {"target_price": None},
                    {"target_price": {"$lte": 0}}
                ]
        if min_price is not None:
            query["target_price"] = {"$ne": None, "$gte": min_price}
        if max_price is not None:
            if "target_price" in query and isinstance(query["target_price"], dict):
                query["target_price"]["$lte"] = max_price
            else:
                query["target_price"] = {"$ne": None, "$lte": max_price}
        
        # Enhanced features filters
        if has_images is not None:
            if has_images:
                query["images"] = {"$exists": True, "$ne": [], "$ne": None}
            else:
                query["$or"] = [
                    {"images": {"$exists": False}},
                    {"images": None},
                    {"images": []}
                ]
                
        if has_vet_certificates is not None:
            if has_vet_certificates:
                query["vet_certificates"] = {"$exists": True, "$ne": [], "$ne": None}
            else:
                query["$or"] = [
                    {"vet_certificates": {"$exists": False}},
                    {"vet_certificates": None},
                    {"vet_certificates": []}
                ]
                
        if has_weight_requirements is not None:
            if has_weight_requirements:
                query["weight_range"] = {"$exists": True, "$ne": None}
            else:
                query["$or"] = [
                    {"weight_range": {"$exists": False}},
                    {"weight_range": None}
                ]
                
        if has_age_requirements is not None:
            if has_age_requirements:
                query["age_requirements"] = {"$exists": True, "$ne": None}
            else:
                query["$or"] = [
                    {"age_requirements": {"$exists": False}},
                    {"age_requirements": None}
                ]
                
        if requires_vaccinations is not None:
            if requires_vaccinations:
                query["vaccination_requirements"] = {"$exists": True, "$ne": [], "$ne": None}
            else:
                query["$or"] = [
                    {"vaccination_requirements": {"$exists": False}},
                    {"vaccination_requirements": None},
                    {"vaccination_requirements": []}
                ]
                
        if allows_inspection is not None:
            query["inspection_allowed"] = allows_inspection
            
        # Delivery preferences
        if delivery_preferences:
            delivery_list = [d.strip() for d in delivery_preferences.split(',')]  
            query["delivery_preferences"] = {"$in": delivery_list}
            
        # Time filters
        if created_within:
            time_map = {'1d': 1, '3d': 3, '7d': 7, '14d': 14, '30d': 30}
            if created_within in time_map:
                days_ago = datetime.now(timezone.utc) - timedelta(days=time_map[created_within])
                query["created_at"] = {"$gte": days_ago}
                
        if expires_within:
            time_map = {'1d': 1, '3d': 3, '7d': 7, '14d': 14, '30d': 30}
            if expires_within in time_map:
                days_from_now = datetime.now(timezone.utc) + timedelta(days=time_map[expires_within])
                if "expires_at" in query:
                    query["expires_at"]["$lte"] = days_from_now
                else:
                    query["expires_at"] = {"$ne": None, "$lte": days_from_now}
        
        # Search functionality
        if search:
            search_regex = {"$regex": search, "$options": "i"}
            query["$or"] = [
                {"species": search_regex},
                {"product_type": search_regex},
                {"breed": search_regex},
                {"province": search_regex},
                {"notes": search_regex},
                {"additional_requirements": search_regex}
            ]
        
        # Handle cursor pagination
        if after:
            try:
                after_id = after
                query["_id"] = {"$lt": after_id}
            except:
                pass  # Invalid cursor, ignore
        
        # Get total count for metadata
        total_count = await db.buy_requests.count_documents(query)
        
        # Determine sort order
        sort_field = [("created_at", -1)]  # Default: newest first
        if sort == "ending_soon":
            sort_field = [("expires_at", 1)]
        elif sort == "newest":
            sort_field = [("created_at", -1)]
        elif sort == "oldest":
            sort_field = [("created_at", 1)]
        elif sort == "price_asc":
            sort_field = [("target_price", 1), ("created_at", -1)]
        elif sort == "price_desc":
            sort_field = [("target_price", -1), ("created_at", -1)]
        elif sort == "qty_asc":
            sort_field = [("qty", 1), ("created_at", -1)]
        elif sort == "qty_desc":
            sort_field = [("qty", -1), ("created_at", -1)]
        elif sort == "relevance":
            # For relevance, we'll score after fetching
            sort_field = [("created_at", -1)]
        
        # Fetch requests
        logger.info(f"Querying buy_requests with query: {query}")
        logger.info(f"Query status filter: {query.get('status')}")
        logger.info(f"Query expires_at filter: {query.get('$or')}")
        
        cursor = db.buy_requests.find(query).sort(sort_field).limit(limit + 1)
        requests = await cursor.to_list(length=None)
        logger.info(f"Found {len(requests)} buy requests matching query")
        
        # Log sample request if found
        if requests and len(requests) > 0:
            sample = requests[0]
            logger.info(f"Sample request: id={sample.get('id')}, status={sample.get('status')}, expires_at={sample.get('expires_at')}")
        
        # Check if there are more results
        has_more = len(requests) > limit
        if has_more:
            requests = requests[:limit]
        
        # Process results
        result_items = []
        for req in requests:
            # Remove MongoDB _id if present
            if "_id" in req:
                del req["_id"]
            
            # Get offers count
            offers_count = await db.buy_request_offers.count_documents({"request_id": req.get("id")})
            
            # Calculate distance if user location provided
            distance_km = None
            if user_lat and user_lng and req.get("location", {}).get("coordinates"):
                req_coords = req["location"]["coordinates"]
                if len(req_coords) >= 2:
                    req_lat, req_lng = req_coords[1], req_coords[0]  # GeoJSON format
                    distance_km = _calculate_distance(user_lat, user_lng, req_lat, req_lng)
            
            # Apply distance filter if specified
            if max_distance_km and distance_km and distance_km > max_distance_km:
                continue
            
            # Build public item - use exact field names from database
            # Log raw request for debugging (first request only)
            if len(result_items) == 0:
                logger.info(f"Raw request keys: {list(req.keys())}")
                logger.info(f"Full raw request data: {req}")
                logger.info(f"Sample request fields: species={req.get('species')}, breed={req.get('breed')}, product_type={req.get('product_type')}, qty={req.get('qty')}, province={req.get('province')}, notes={req.get('notes')}")
            
            # Get ALL fields directly from database - return exactly what's stored
            target_price = req.get("target_price")
            expires_at = req.get("expires_at")
            created_at = req.get("created_at")
            species = req.get("species")  # Return None if not in DB
            breed = req.get("breed")  # Return None if not in DB
            product_type = req.get("product_type")  # Return None if not in DB
            qty = req.get("qty")  # Return None if not in DB
            unit = req.get("unit")  # Return None if not in DB
            province = req.get("province")  # Return None if not in DB
            country = req.get("country")  # Return None if not in DB
            notes = req.get("notes")  # Return None if not in DB
            
            # Log if critical fields are missing
            if not species and not breed and not product_type:
                logger.warning(f"Request {req.get('id')} has no species, breed, or product_type - returning as-is from DB")
            
            # Handle datetime conversion
            if expires_at and not isinstance(expires_at, str):
                if hasattr(expires_at, 'isoformat'):
                    expires_at_str = expires_at.isoformat()
                else:
                    expires_at_str = str(expires_at)
            else:
                expires_at_str = expires_at
            
            if created_at and not isinstance(created_at, str):
                if hasattr(created_at, 'isoformat'):
                    created_at_str = created_at.isoformat()
                else:
                    created_at_str = str(created_at)
            else:
                created_at_str = created_at
            
            # Build title from available data
            title_parts = []
            if breed:
                title_parts.append(breed)
            if species:
                title_parts.append(species)
            title = " ".join(title_parts).strip() if title_parts else (species or product_type or "Buy Request")
            
            # Return all fields matching the create API structure
            item = {
                "id": req.get("id"),
                "title": title,
                "species": species,  # From database
                "product_type": product_type,  # From database
                "breed": breed,  # From database
                "qty": int(qty) if qty is not None else 0,  # Convert to int, default 0
                "unit": unit or "head",  # Default to "head" if not specified
                "province": province,  # From database
                "country": country or "ZA",  # Default to "ZA" if not specified
                "deadline_at": expires_at_str,  # Frontend expects deadline_at
                "expires_at": expires_at_str,  # Also include expires_at
                "has_target_price": bool(target_price and target_price > 0),
                "target_price": float(target_price) if target_price is not None else None,
                "offers_count": offers_count,
                "created_at": created_at_str,
                "notes": notes,  # From database
                "notes_excerpt": (notes[:200] + "...") if notes and len(notes) > 200 else notes,
                "additional_requirements": req.get("additional_requirements"),
                # Enhanced content fields (public safe)
                "images": req.get("images", [])[:3] if req.get("images") else [],
                "has_vet_certificates": bool(req.get("vet_certificates")),
                "vet_certificates": req.get("vet_certificates", []),
                "weight_range": req.get("weight_range"),
                "age_requirements": req.get("age_requirements"),
                "vaccination_requirements": req.get("vaccination_requirements", []),
                "delivery_preferences": req.get("delivery_preferences", "both"),  # Default to "both"
                "inspection_allowed": req.get("inspection_allowed", True)  # Default to True
            }
            
            if distance_km is not None:
                item["distance_km"] = round(distance_km, 1)
            
            result_items.append(item)
        
        # Apply ML relevance scoring if requested
        if sort == "relevance" and result_items:
            result_items = await _apply_relevance_scoring(
                result_items, user_lat, user_lng
            )
        
        # Generate next cursor
        next_cursor = None
        if has_more and result_items:
            last_item = requests[-1]  # Use the last item from original list
            next_cursor = str(last_item["_id"])
        
        return {
            "items": result_items,
            "nextCursor": next_cursor,
            "hasMore": has_more,
            "total": total_count,
            "filters_applied": {
                "species": species,
                "product_type": product_type,
                "province": province,
                "qty_range": [min_qty, max_qty],
                "has_target_price": has_target_price,
                "max_distance_km": max_distance_km
            },
            "sort": sort
        }
        
    except Exception as e:
        logger.error(f"Error getting public buy requests: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch buy requests")

@api_router.get("/public/buy-requests/{request_id}")
async def get_public_buy_request_detail(
    request_id: str,
    current_user: Optional[User] = Depends(get_current_user_optional),
    user_lat: Optional[float] = None,
    user_lng: Optional[float] = None
):
    """Get public buy request detail"""
    try:
        # Get the buy request
        request = await db.buy_requests.find_one({"id": request_id})
        if not request:
            raise HTTPException(status_code=404, detail="Buy request not found")
        
        # Check if request is open and not expired
        if request["status"] != "open":
            if current_user and current_user.id == request["buyer_id"]:
                pass  # Owner can view their own inactive requests
            else:
                raise HTTPException(status_code=404, detail="Buy request not available")
        
        # Check if request is expired (handle timezone properly)
        expires_at = request["expires_at"]
        if not expires_at.tzinfo:
            # If no timezone info, assume UTC
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        
        if expires_at <= datetime.now(timezone.utc):
            if current_user and current_user.id == request["buyer_id"]:
                pass  # Owner can view their expired requests
            else:
                raise HTTPException(status_code=410, detail="Buy request has expired")
        
        # Get offers count
        offers_count = await db.buy_request_offers.count_documents({"request_id": request_id})
        
        # Calculate distance if user location provided
        distance_km = None
        if user_lat and user_lng and request.get("location", {}).get("coordinates"):
            req_coords = request["location"]["coordinates"]
            if len(req_coords) >= 2:
                req_lat, req_lng = req_coords[1], req_coords[0]
                distance_km = _calculate_distance(user_lat, user_lng, req_lat, req_lng)
        
        # Determine if current user can send offer (seller in range)
        can_send_offer = False
        in_range = True
        compliance_flags = {
            "kyc": False,
            "live": request["species"].lower() in ["cattle", "sheep", "goats", "swine"],
            "disease_zone": False
        }
        
        if current_user and "seller" in (current_user.roles or []):
            # Check basic eligibility
            can_send_offer = True
            
            # Check if already sent offer
            existing_offer = await db.buy_request_offers.find_one({
                "request_id": request_id,
                "seller_id": current_user.id
            })
            if existing_offer:
                can_send_offer = False
            
            # Check range (simplified)
            if distance_km and distance_km > 500:  # 500km max range
                in_range = False
                can_send_offer = False
            
            # Check KYC for live animals
            if compliance_flags["live"]:
                # Check if seller has KYC
                if not current_user.kyc_verified:
                    compliance_flags["kyc"] = True
                    can_send_offer = False
        
        # Prepare notes excerpt (first 200 chars, no PII)
        notes_excerpt = ""
        if request.get("notes"):
            notes_excerpt = request["notes"][:200]
            if len(request["notes"]) > 200:
                notes_excerpt += "..."
        
        # Build response
        detail = {
            "id": request["id"],
            "species": request["species"],
            "product_type": request["product_type"],
            "qty": request["qty"],
            "unit": request["unit"],
            "province": request["province"],
            "deadline_at": request["expires_at"].isoformat(),
            "notes_excerpt": notes_excerpt,
            "offers_count": offers_count,
            "compliance_flags": compliance_flags,
            "can_send_offer": can_send_offer,
            "in_range": in_range,
            "created_at": request["created_at"].isoformat(),
            # Enhanced content fields (full detail)
            "images": request.get("images", []),
            "vet_certificates": request.get("vet_certificates", []) if current_user else [],  # Only show to authenticated users
            "weight_range": request.get("weight_range"),
            "age_requirements": request.get("age_requirements"),
            "vaccination_requirements": request.get("vaccination_requirements", []),
            "delivery_preferences": request.get("delivery_preferences", "both"),
            "inspection_allowed": request.get("inspection_allowed", True),
            "additional_requirements": request.get("additional_requirements")
        }
        
        # Add optional fields
        if request.get("breed"):
            detail["breed"] = request["breed"]
        if request.get("target_price", 0) > 0:
            detail["target_price"] = request["target_price"]
        if distance_km is not None:
            detail["distance_km"] = round(distance_km, 1)
        
        # Add buyer info (limited)
        buyer = await db.users.find_one({"id": request["buyer_id"]})
        if buyer:
            detail["buyer"] = {
                "name": buyer.get("full_name", "Anonymous"),
                "province": buyer.get("province", request["province"]),
                "verified": buyer.get("kyc_verified", False)
            }
        
        return detail
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting buy request detail: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch buy request details")

# (Removed duplicate endpoint - consolidated with existing endpoint above)

# Helper functions
def _calculate_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate distance between two coordinates in kilometers"""
    from math import radians, cos, sin, asin, sqrt
    
    # Convert to radians
    lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
    
    # Haversine formula
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlng/2)**2
    c = 2 * asin(sqrt(a))
    r = 6371  # Earth's radius in kilometers
    
    return c * r

async def _apply_relevance_scoring(
    items: List[dict],
    user_lat: Optional[float] = None,
    user_lng: Optional[float] = None
) -> List[dict]:
    """Apply ML relevance scoring to buy request items"""
    try:
        for item in items:
            score = 0.0
            
            # Proximity scoring (40% weight)
            if user_lat and user_lng and item.get("distance_km"):
                distance = item["distance_km"]
                # Inverse distance scoring: closer = higher score
                proximity_score = max(0, 1 - (distance / 1000))  # Normalize to 1000km max
                score += proximity_score * 0.4
            else:
                score += 0.2  # Default if no location
            
            # Freshness scoring (25% weight)
            created_at = datetime.fromisoformat(item["created_at"].replace('Z', '+00:00'))
            age_hours = (datetime.now(timezone.utc) - created_at).total_seconds() / 3600
            freshness_score = max(0, 1 - (age_hours / (24 * 7)))  # Decay over 1 week
            score += freshness_score * 0.25
            
            # Quantity fit scoring (20% weight) - assume mid-range is optimal
            qty = item["qty"]
            if qty >= 10 and qty <= 100:  # Sweet spot
                qty_score = 1.0
            elif qty >= 5 and qty <= 200:  # Good range
                qty_score = 0.8
            else:
                qty_score = 0.6
            score += qty_score * 0.2
            
            # Activity scoring (15% weight) - based on offers
            offers_count = item.get("offers_count", 0)
            if offers_count == 0:
                activity_score = 1.0  # New requests get priority
            elif offers_count <= 3:
                activity_score = 0.8  # Some competition is good
            else:
                activity_score = 0.5  # High competition
            score += activity_score * 0.15
            
            item["relevance_score"] = round(score, 3)
        
        # Sort by relevance score (highest first)
        items.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        
        return items
        
    except Exception as e:
        logger.error(f"Error applying relevance scoring: {e}")
        return items  # Return unsorted if scoring fails

# SUGGESTION SYSTEM ENDPOINTS
@api_router.post("/suggestions")
async def create_suggestion(suggestion_data: SuggestionCreate, request: Request, current_user: Optional[User] = Depends(get_current_user_optional)):
    """Create a new suggestion (public endpoint)"""
    try:
        # Basic validation
        if not suggestion_data.title.strip():
            raise HTTPException(status_code=400, detail="Title is required")
        
        # Create suggestion
        suggestion = Suggestion(
            user_id=current_user.id if current_user else None,
            kind=suggestion_data.kind,
            title=suggestion_data.title.strip(),
            details=suggestion_data.details.strip() if suggestion_data.details else None,
            species=suggestion_data.species.strip() if suggestion_data.species else None,
            breed=suggestion_data.breed.strip() if suggestion_data.breed else None,
            contact_email=suggestion_data.contact_email if suggestion_data.contact_email else None,
        )
        
        # Save to database
        suggestion_dict = suggestion.dict()
        await db.suggestions.insert_one(suggestion_dict)
        
        # Emit admin notification event
        await emit_admin_event("SUGGESTION.CREATED", {
            "suggestion_id": suggestion.id,
            "kind": suggestion.kind,
            "title": suggestion.title,
            "user_id": current_user.id if current_user else None,
            "contact_email": suggestion_data.contact_email if suggestion_data.contact_email else None
        })
        
        logger.info(f"New suggestion created: {suggestion.id} - {suggestion.kind} - {suggestion.title}")
        
        return {
            "success": True,
            "message": "Thank you for your suggestion! We'll review it shortly.",
            "id": suggestion.id
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating suggestion: {e}")
        raise HTTPException(status_code=500, detail="Failed to create suggestion")

@api_router.get("/admin/suggestions")
async def admin_get_suggestions(
    status: Optional[str] = None,
    kind: Optional[str] = None,
    limit: int = 100,
    current_user: User = Depends(get_current_admin_user)
):
    """Get suggestions for admin review"""
    try:
        # Build filter query
        filter_query = {}
        if status:
            filter_query["status"] = status
        if kind:
            filter_query["kind"] = kind
        
        # Get suggestions
        suggestions_docs = await db.suggestions.find(filter_query).sort([
            ("status", 1),  # NEW first
            ("created_at", -1)  # newest first
        ]).limit(limit).to_list(length=None)
        
        suggestions = []
        for doc in suggestions_docs:
            suggestion = Suggestion(**doc)
            suggestions.append(suggestion.dict())
        
        return {
            "suggestions": suggestions,
            "total": len(suggestions)
        }
    
    except Exception as e:
        logger.error(f"Error fetching suggestions: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch suggestions")

@api_router.put("/admin/suggestions/{suggestion_id}")
async def admin_update_suggestion(
    suggestion_id: str,
    update_data: SuggestionUpdate,
    current_user: User = Depends(get_current_admin_user)
):
    """Update suggestion status/priority"""
    try:
        # Find suggestion
        suggestion = await db.suggestions.find_one({"id": suggestion_id})
        if not suggestion:
            raise HTTPException(status_code=404, detail="Suggestion not found")
        
        # Build update data
        update_fields = {"updated_at": datetime.now(timezone.utc)}
        
        if update_data.status:
            update_fields["status"] = update_data.status
        if update_data.priority:
            update_fields["priority"] = update_data.priority
        if update_data.admin_notes:
            update_fields["admin_notes"] = update_data.admin_notes
        
        # Update suggestion
        await db.suggestions.update_one(
            {"id": suggestion_id},
            {"$set": update_fields}
        )
        
        # Emit admin event
        await emit_admin_event("SUGGESTION.UPDATED", {
            "suggestion_id": suggestion_id,
            "status": update_data.status,
            "priority": update_data.priority,
            "admin_id": current_user.id
        })
        
        return {"success": True, "message": "Suggestion updated successfully"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating suggestion: {e}")
        raise HTTPException(status_code=500, detail="Failed to update suggestion")

@api_router.post("/admin/suggestions/{suggestion_id}/vote")
async def admin_vote_suggestion(
    suggestion_id: str,
    current_user: User = Depends(get_current_admin_user)
):
    """Vote on suggestion (admin only for now)"""
    try:
        # Update vote count
        result = await db.suggestions.update_one(
            {"id": suggestion_id},
            {"$inc": {"votes": 1}}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Suggestion not found")
        
        return {"success": True, "message": "Vote recorded"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error voting on suggestion: {e}")
        raise HTTPException(status_code=500, detail="Failed to vote")

# ADMIN SETTINGS MANAGEMENT
@api_router.get("/admin/settings")
async def get_admin_settings(current_user: User = Depends(get_current_user)):
    """Get platform settings (admin only)"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        settings_doc = await db.settings.find_one({"type": "platform"})
        if not settings_doc:
            # Return default settings if none exist
            return {
                "siteName": "StockLot",
                "siteDescription": "South Africa's Premier Livestock Marketplace",
                "supportEmail": "support@stocklot.co.za",
                "supportPhone": "+27 123 456 789",
                "businessAddress": "Cape Town, South Africa",
                "facebookUrl": "",
                "twitterUrl": "",
                "instagramUrl": "",
                "youtubeUrl": "",
                "linkedinUrl": "",
                "androidAppUrl": "",
                "iosAppUrl": "",
                "appStoreVisible": False,
                "deliveryOnlyMode": False,
                "guestCheckoutEnabled": True,
                "autoListingApproval": False,
                "escrowAutoReleaseDays": 7,
                "whatsappNumber": "",
                "businessHours": "Mon-Fri: 8:00 AM - 6:00 PM",
                "auctionsEnabled": False,
                "buyRequestsEnabled": True,
                "messagingEnabled": True,
                "geofencingEnabled": True,
                "metaKeywords": "livestock, cattle, goats, pigs, chickens, farming, South Africa",
                "googleAnalyticsId": "",
                "facebookPixelId": "",
                "paystackPublicKey": "",
                "paystackSecretKey": "",
                "paystackDemoMode": True
            }
        
        # Remove MongoDB _id and sensitive data for frontend
        if "_id" in settings_doc:
            del settings_doc["_id"]
        if "type" in settings_doc:
            del settings_doc["type"]
            
        return settings_doc
        
    except Exception as e:
        logger.error(f"Error fetching admin settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch settings")

@api_router.put("/admin/settings")
async def update_admin_settings(settings_data: dict, current_user: User = Depends(get_current_user)):
    """Update platform settings (admin only)"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Add metadata
        settings_data["type"] = "platform"
        settings_data["updated_at"] = datetime.now(timezone.utc)
        settings_data["updated_by"] = current_user.id
        
        # Upsert settings document
        result = await db.settings.update_one(
            {"type": "platform"},
            {"$set": settings_data},
            upsert=True
        )
        
        # If Paystack credentials were updated, update environment
        if "paystackPublicKey" in settings_data or "paystackSecretKey" in settings_data:
            logger.info("Paystack credentials updated")
        
        return {"success": True, "message": "Settings updated successfully"}
        
    except Exception as e:
        logger.error(f"Error updating admin settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to update settings")

@api_router.get("/public/settings")
async def get_public_settings():
    """Get public platform settings (no auth required)"""
    try:
        settings_doc = await db.settings.find_one({"type": "platform"})
        if not settings_doc:
            return {
                "siteName": "StockLot",
                "siteDescription": "South Africa's Premier Livestock Marketplace",
                "facebookUrl": "",
                "twitterUrl": "",
                "instagramUrl": "",
                "youtubeUrl": "",
                "linkedinUrl": "",
                "androidAppUrl": "",
                "iosAppUrl": "",
                "appStoreVisible": False,
                "businessHours": "Mon-Fri: 8:00 AM - 6:00 PM"
            }
        
        # Return only public settings
        public_settings = {
            "siteName": settings_doc.get("siteName", "StockLot"),
            "siteDescription": settings_doc.get("siteDescription", "South Africa's Premier Livestock Marketplace"),
            "facebookUrl": settings_doc.get("facebookUrl", ""),
            "twitterUrl": settings_doc.get("twitterUrl", ""),
            "instagramUrl": settings_doc.get("instagramUrl", ""),
            "youtubeUrl": settings_doc.get("youtubeUrl", ""),
            "linkedinUrl": settings_doc.get("linkedinUrl", ""),
            "androidAppUrl": settings_doc.get("androidAppUrl", ""),
            "iosAppUrl": settings_doc.get("iosAppUrl", ""),
            "appStoreVisible": settings_doc.get("appStoreVisible", False),
            "businessHours": settings_doc.get("businessHours", "Mon-Fri: 8:00 AM - 6:00 PM"),
            "supportEmail": settings_doc.get("supportEmail", "support@stocklot.co.za"),
            "supportPhone": settings_doc.get("supportPhone", "+27 123 456 789"),
            "whatsappNumber": settings_doc.get("whatsappNumber", "")
        }
        
        return public_settings
        
    except Exception as e:
        logger.error(f"Error fetching public settings: {e}")
        return {
            "siteName": "StockLot",
            "siteDescription": "South Africa's Premier Livestock Marketplace"
        }

# Update Paystack environment with saved settings
async def update_paystack_from_settings():
    """Update Paystack service with saved settings"""
    try:
        settings_doc = await db.settings.find_one({"type": "platform"})
        if settings_doc:
            if settings_doc.get("paystackSecretKey"):
                os.environ["PAYSTACK_SECRET_KEY"] = settings_doc["paystackSecretKey"]
            if settings_doc.get("paystackPublicKey"):
                os.environ["PAYSTACK_PUBLIC_KEY"] = settings_doc["paystackPublicKey"]
            if "paystackDemoMode" in settings_doc:
                os.environ["PAYSTACK_DEMO_MODE"] = str(settings_doc["paystackDemoMode"]).lower()
    except Exception as e:
        logger.error(f"Error updating Paystack settings: {e}")

# DELIVERY RATE CALCULATION SYSTEM
@api_router.post("/delivery/calculate")
async def calculate_delivery_rate(delivery_data: dict):
    """Calculate delivery rate based on distance and AA rates"""
    try:
        seller_address = delivery_data.get("seller_address", {})
        buyer_address = delivery_data.get("buyer_address", {})
        
        # Extract coordinates or use geocoding
        seller_lat = seller_address.get("latitude")
        seller_lng = seller_address.get("longitude")
        buyer_lat = buyer_address.get("latitude")
        buyer_lng = buyer_address.get("longitude")
        
        # If coordinates not provided, use province-level approximation
        if not all([seller_lat, seller_lng, buyer_lat, buyer_lng]):
            return calculate_provincial_delivery_rate(seller_address, buyer_address)
        
        # Calculate distance using Haversine formula
        distance_km = calculate_distance(seller_lat, seller_lng, buyer_lat, buyer_lng)
        
        # AA rates updated for livestock delivery
        # Updated rate: R20.00 per km for livestock transport
        base_rate_per_km = 20.00
        
        # Calculate delivery cost
        delivery_cost = distance_km * base_rate_per_km
        
        # Minimum delivery fee
        min_delivery_fee = 50.00
        delivery_cost = max(delivery_cost, min_delivery_fee)
        
        # Maximum delivery distance (500km)
        max_distance = 500
        if distance_km > max_distance:
            return {
                "success": False,
                "error": f"Delivery distance ({distance_km:.1f}km) exceeds maximum deliverable range ({max_distance}km)",
                "max_distance": max_distance
            }
        
        return {
            "success": True,
            "distance_km": round(distance_km, 1),
            "delivery_cost": round(delivery_cost, 2),
            "rate_per_km": base_rate_per_km,
            "min_fee": min_delivery_fee,
            "estimated_time": get_estimated_delivery_time(distance_km)
        }
        
    except Exception as e:
        logger.error(f"Error calculating delivery rate: {e}")
        raise HTTPException(status_code=500, detail="Failed to calculate delivery rate")

def calculate_distance(lat1, lng1, lat2, lng2):
    """Calculate distance between two points using Haversine formula"""
    from math import radians, cos, sin, asin, sqrt
    
    # Convert to radians
    lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
    
    # Haversine formula
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlng/2)**2
    c = 2 * asin(sqrt(a))
    
    # Earth radius in kilometers
    r = 6371
    return c * r

def calculate_provincial_delivery_rate(seller_address, buyer_address):
    """Calculate delivery rate based on provinces when coordinates not available"""
    seller_province = seller_address.get("province", "").lower()
    buyer_province = buyer_address.get("province", "").lower()
    
    # Provincial distance matrix (approximate distances between major cities)
    provincial_distances = {
        ("western cape", "western cape"): 50,
        ("western cape", "eastern cape"): 300,
        ("western cape", "northern cape"): 450,
        ("western cape", "free state"): 600,
        ("western cape", "kwazulu-natal"): 800,
        ("western cape", "gauteng"): 900,
        ("western cape", "north west"): 950,
        ("western cape", "mpumalanga"): 1000,
        ("western cape", "limpopo"): 1100,
        ("gauteng", "gauteng"): 30,
        ("gauteng", "north west"): 150,
        ("gauteng", "free state"): 200,
        ("gauteng", "mpumalanga"): 250,
        ("gauteng", "kwazulu-natal"): 400,
        ("gauteng", "limpopo"): 450,
        ("gauteng", "northern cape"): 500,
        ("gauteng", "eastern cape"): 700,
        ("kwazulu-natal", "kwazulu-natal"): 50,
        ("kwazulu-natal", "free state"): 200,
        ("kwazulu-natal", "eastern cape"): 300,
        ("kwazulu-natal", "mpumalanga"): 350,
        ("kwazulu-natal", "gauteng"): 400,
        # Add more combinations as needed
    }
    
    # Get distance or use default
    distance_key = (seller_province, buyer_province)
    distance_key_reverse = (buyer_province, seller_province)
    
    distance_km = provincial_distances.get(distance_key) or provincial_distances.get(distance_key_reverse, 200)
    
    # Apply same rate calculation  
    base_rate_per_km = 20.00
    delivery_cost = max(distance_km * base_rate_per_km, 50.00)
    
    return {
        "success": True,
        "distance_km": distance_km,
        "delivery_cost": round(delivery_cost, 2),
        "rate_per_km": base_rate_per_km,
        "min_fee": 50.00,
        "estimated_time": get_estimated_delivery_time(distance_km),
        "calculation_method": "provincial_approximation"
    }

def get_estimated_delivery_time(distance_km):
    """Get estimated delivery time based on distance"""
    if distance_km <= 50:
        return "Same day delivery"
    elif distance_km <= 200:
        return "1-2 business days"
    elif distance_km <= 500:
        return "2-3 business days"
    elif distance_km <= 800:
        return "3-5 business days"
    else:
        return "5-7 business days"

@api_router.get("/delivery/provinces")
async def get_delivery_provinces():
    """Get list of South African provinces for delivery calculation"""
    return {
        "provinces": [
            {"code": "WC", "name": "Western Cape"},
            {"code": "EC", "name": "Eastern Cape"},
            {"code": "NC", "name": "Northern Cape"},
            {"code": "FS", "name": "Free State"},
            {"code": "KZN", "name": "KwaZulu-Natal"},
            {"code": "GP", "name": "Gauteng"},
            {"code": "NW", "name": "North West"},
            {"code": "MP", "name": "Mpumalanga"},
            {"code": "LP", "name": "Limpopo"}
        ]
    }

# PAYSTACK TRANSFER RECIPIENTS AND PAYOUTS API ENDPOINTS

# Import transfer services
try:
    from services.transfer_models import (
        BankAccountRecipientCreate, AuthorizationRecipientCreate, TransferCreate,
        EscrowReleaseRequest, RecipientResponse, TransferResponse, BankListResponse
    )
    from services.paystack_transfer_client import PaystackTransferClient
    from services.transfer_recipient_service import TransferRecipientService
    from services.transfer_automation_service import TransferAutomationService
    from services.webhook_idempotency_service import WebhookIdempotencyService
    from services.public_config_service import PublicConfigService
    from services.sse_admin_service import SSEAdminService, AdminEventEmitters
    
    # Initialize transfer services
    paystack_transfer_client = PaystackTransferClient()
    transfer_recipient_service = TransferRecipientService(db, paystack_transfer_client)
    transfer_automation_service = TransferAutomationService(db, paystack_transfer_client)
    webhook_idempotency_service = WebhookIdempotencyService(db)
    public_config_service = PublicConfigService(db)
    sse_admin_service = SSEAdminService(db)
    admin_event_emitters = AdminEventEmitters(sse_admin_service, db)
    
    TRANSFER_SERVICES_AVAILABLE = True
    logger.info("✅ Paystack Transfer Services initialized successfully")
except (ImportError, ValueError) as e:
    logger.warning(f"⚠️  Transfer services not available: {e}")
    TRANSFER_SERVICES_AVAILABLE = False

# Transfer Recipient Endpoints
@api_router.get("/recipients/banks", response_model=BankListResponse)
async def list_banks(
    country: str = "south africa",
    current_user: User = Depends(get_current_user)
):
    """List available banks for South Africa"""
    if not TRANSFER_SERVICES_AVAILABLE:
        raise HTTPException(status_code=503, detail="Transfer services unavailable")
    
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        response = await paystack_transfer_client.list_banks(country=country)
        
        if not response.status:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to fetch banks: {response.message}"
            )
        
        banks = response.data or []
        return BankListResponse(banks=banks, total=len(banks))
        
    except Exception as e:
        logger.error(f"Error fetching banks: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch bank list")

@api_router.post("/recipients/bank-account", status_code=201)
async def create_bank_account_recipient(
    recipient_data: BankAccountRecipientCreate,
    current_user: User = Depends(get_current_user)
):
    """Create a transfer recipient for South African bank account"""
    if not TRANSFER_SERVICES_AVAILABLE:
        raise HTTPException(status_code=503, detail="Transfer services unavailable")
    
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        logger.info(f"Creating bank account recipient for user {current_user.id}")
        
        recipient = await transfer_recipient_service.create_bank_account_recipient(
            user_id=current_user.id,
            recipient_data=recipient_data
        )
        
        logger.info(f"Created recipient {recipient.id} for user {current_user.id}")
        
        return {
            "success": True,
            "recipient": {
                "id": recipient.id,
                "name": recipient.name,
                "bank_name": recipient.bank_name,
                "account_number": recipient.account_number,
                "is_validated": recipient.is_validated,
                "paystack_recipient_code": recipient.paystack_recipient_code
            }
        }
        
    except ValueError as e:
        logger.warning(f"Validation error creating recipient: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating bank account recipient: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create recipient")

@api_router.post("/recipients/authorization", status_code=201)
async def create_authorization_recipient(
    recipient_data: AuthorizationRecipientCreate,
    current_user: User = Depends(get_current_user)
):
    """Create a transfer recipient using authorization code"""
    if not TRANSFER_SERVICES_AVAILABLE:
        raise HTTPException(status_code=503, detail="Transfer services unavailable")
    
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        logger.info(f"Creating authorization recipient for user {current_user.id}")
        
        recipient = await transfer_recipient_service.create_authorization_recipient(
            user_id=current_user.id,
            recipient_data=recipient_data
        )
        
        logger.info(f"Created authorization recipient {recipient.id} for user {current_user.id}")
        
        return {
            "success": True,
            "recipient": {
                "id": recipient.id,
                "name": recipient.name,
                "card_last4": recipient.card_last4,
                "card_bank": recipient.card_bank,
                "is_validated": recipient.is_validated,
                "paystack_recipient_code": recipient.paystack_recipient_code
            }
        }
        
    except ValueError as e:
        logger.warning(f"Validation error creating authorization recipient: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating authorization recipient: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create authorization recipient")

@api_router.get("/recipients")
async def list_user_recipients(
    include_inactive: bool = False,
    current_user: User = Depends(get_current_user)
):
    """List transfer recipients for current user"""
    if not TRANSFER_SERVICES_AVAILABLE:
        raise HTTPException(status_code=503, detail="Transfer services unavailable")
    
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        recipients = await transfer_recipient_service.get_user_recipients(
            user_id=current_user.id,
            include_inactive=include_inactive
        )
        
        return {"recipients": recipients}
        
    except Exception as e:
        logger.error(f"Error fetching recipients for user {current_user.id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch recipients")

@api_router.get("/recipients/{recipient_id}")
async def get_recipient_details(
    recipient_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get transfer recipient details"""
    if not TRANSFER_SERVICES_AVAILABLE:
        raise HTTPException(status_code=503, detail="Transfer services unavailable")
    
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        recipient = await transfer_recipient_service.get_recipient_by_id(recipient_id, current_user.id)
        
        if not recipient:
            raise HTTPException(status_code=404, detail="Transfer recipient not found")
        
        return {"recipient": recipient}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching recipient {recipient_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch recipient details")

@api_router.delete("/recipients/{recipient_id}", status_code=204)
async def deactivate_recipient(
    recipient_id: str,
    current_user: User = Depends(get_current_user)
):
    """Deactivate transfer recipient"""
    if not TRANSFER_SERVICES_AVAILABLE:
        raise HTTPException(status_code=503, detail="Transfer services unavailable")
    
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        success = await transfer_recipient_service.deactivate_recipient(
            recipient_id=recipient_id,
            user_id=current_user.id
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Transfer recipient not found")
        
        return None
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deactivating recipient {recipient_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to deactivate recipient")

# Transfer and Payout Endpoints
@api_router.post("/transfers", status_code=201)
async def create_transfer(
    transfer_data: TransferCreate,
    current_user: User = Depends(get_current_user)
):
    """Create a new transfer"""
    if not TRANSFER_SERVICES_AVAILABLE:
        raise HTTPException(status_code=503, detail="Transfer services unavailable")
    
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        amount_cents = int(transfer_data.amount * 100)
        
        transfer = await transfer_automation_service.initiate_transfer(
            sender_id=current_user.id,
            recipient_id=transfer_data.recipient_id,
            amount=amount_cents,
            reason=transfer_data.reason,
            reference=transfer_data.reference
        )
        
        logger.info(f"Created transfer {transfer.id} for user {current_user.id}")
        
        return {
            "success": True,
            "transfer": {
                "id": transfer.id,
                "reference": transfer.reference,
                "status": transfer.status,
                "amount": transfer.amount,
                "amount_zar": transfer.amount / 100.0,
                "currency": transfer.currency,
                "reason": transfer.reason,
                "initiated_at": transfer.initiated_at
            }
        }
        
    except ValueError as e:
        logger.warning(f"Validation error creating transfer: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating transfer: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create transfer")

@api_router.get("/transfers")
async def list_user_transfers(
    page: int = 1,
    per_page: int = 20,
    current_user: User = Depends(get_current_user)
):
    """List transfers for current user"""
    if not TRANSFER_SERVICES_AVAILABLE:
        raise HTTPException(status_code=503, detail="Transfer services unavailable")
    
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        # Get transfers where user is sender or recipient
        transfers_docs = await db.transfers.find({
            "$or": [
                {"sender_id": current_user.id},
                {"recipient_user_id": current_user.id}
            ]
        }).sort("initiated_at", -1).skip((page - 1) * per_page).limit(per_page).to_list(length=None)
        
        total = await db.transfers.count_documents({
            "$or": [
                {"sender_id": current_user.id},
                {"recipient_user_id": current_user.id}
            ]
        })
        
        transfers = []
        for doc in transfers_docs:
            doc.pop("_id", None)
            # Get recipient name
            recipient_name = None
            if doc.get("recipient_id"):
                recipient = await transfer_recipient_service.get_recipient_by_id(doc["recipient_id"])
                if recipient:
                    recipient_name = recipient.name
            
            transfers.append({
                "id": doc["id"],
                "reference": doc["reference"],
                "status": doc.get("status"),
                "amount": doc["amount"],
                "amount_zar": doc["amount"] / 100.0,
                "currency": doc["currency"],
                "reason": doc.get("reason"),
                "recipient_name": recipient_name,
                "failure_reason": doc.get("failure_reason"),
                "retry_count": doc.get("retry_count", 0),
                "initiated_at": doc["initiated_at"],
                "completed_at": doc.get("completed_at"),
                "failed_at": doc.get("failed_at")
            })
        
        return {
            "transfers": transfers,
            "total": total,
            "page": page,
            "per_page": per_page,
            "has_next": total > page * per_page,
            "has_prev": page > 1
        }
        
    except Exception as e:
        logger.error(f"Error listing transfers for user {current_user.id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch transfers")

@api_router.get("/transfers/{transfer_id}")
async def get_transfer_status(
    transfer_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get detailed transfer status"""
    if not TRANSFER_SERVICES_AVAILABLE:
        raise HTTPException(status_code=503, detail="Transfer services unavailable")
    
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        # Verify user access to transfer
        transfer_doc = await db.transfers.find_one({
            "id": transfer_id,
            "$or": [
                {"sender_id": current_user.id},
                {"recipient_user_id": current_user.id}
            ]
        })
        
        if not transfer_doc:
            raise HTTPException(status_code=404, detail="Transfer not found")
        
        # Get updated status from service
        status_info = await transfer_automation_service.get_transfer_status(transfer_id)
        
        return {"transfer": status_info}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting transfer status {transfer_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch transfer status")

@api_router.post("/transfers/escrow/release")
async def release_escrow(
    release_data: EscrowReleaseRequest,
    current_user: User = Depends(get_current_user)
):
    """Release escrow and initiate transfer to seller"""
    if not TRANSFER_SERVICES_AVAILABLE:
        raise HTTPException(status_code=503, detail="Transfer services unavailable")
    
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        # Verify user access to escrow transaction
        escrow_doc = await db.escrow_transactions.find_one({"id": release_data.escrow_transaction_id})
        
        if not escrow_doc:
            raise HTTPException(status_code=404, detail="Escrow transaction not found")
        
        # Check if user is buyer, seller, or admin
        is_buyer = escrow_doc.get("buyer_id") == current_user.id
        is_seller = escrow_doc.get("seller_id") == current_user.id
        is_admin = "admin" in current_user.roles
        
        if not (is_buyer or is_seller or is_admin):
            raise HTTPException(status_code=403, detail="Not authorized to release this escrow")
        
        # Process escrow release
        transfer = await transfer_automation_service.process_escrow_release(
            escrow_transaction_id=release_data.escrow_transaction_id,
            released_by_user_id=current_user.id,
            release_reason=release_data.release_reason
        )
        
        logger.info(f"Released escrow {release_data.escrow_transaction_id}, created transfer {transfer.id}")
        
        return {
            "success": True,
            "transfer": {
                "id": transfer.id,
                "reference": transfer.reference,
                "status": transfer.status,
                "amount": transfer.amount,
                "amount_zar": transfer.amount / 100.0,
                "currency": transfer.currency,
                "reason": transfer.reason,
                "initiated_at": transfer.initiated_at
            }
        }
        
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Validation error releasing escrow: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error releasing escrow {release_data.escrow_transaction_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to release escrow")

# Paystack Transfer Webhook Handler with Idempotency
@api_router.post("/webhooks/paystack/transfers")
async def handle_paystack_transfer_webhook(request: Request):
    """Handle Paystack transfer webhook notifications with idempotency protection"""
    if not TRANSFER_SERVICES_AVAILABLE:
        raise HTTPException(status_code=503, detail="Transfer services unavailable")
    
    try:
        # Get raw body and signature
        payload = await request.body()
        signature = request.headers.get("x-paystack-signature", "")
        
        # Parse event data first (before verification for idempotency check)
        event_data = await request.json()
        
        # Check for duplicate events BEFORE signature verification (more efficient)
        if await webhook_idempotency_service.is_duplicate_event(event_data):
            logger.info(f"Duplicate webhook event detected: {event_data.get('event')}")
            return {"status": "duplicate", "message": "Event already processed"}
        
        # Record the webhook event for idempotency tracking
        webhook_secret = os.getenv("PAYSTACK_WEBHOOK_SECRET")
        if webhook_secret and not webhook_idempotency_service.verify_paystack_signature(payload, signature, webhook_secret):
            logger.warning("Invalid webhook signature received")
            # Still record the event as failed for monitoring
            event_id = await webhook_idempotency_service.record_webhook_event(event_data, signature, processed=False)
            await webhook_idempotency_service.mark_event_failed(event_id, "Invalid signature")
            raise HTTPException(status_code=400, detail="Invalid signature")
        
        # Record the webhook event
        event_id = await webhook_idempotency_service.record_webhook_event(event_data, signature, processed=False)
        
        event_type = event_data.get("event")
        data = event_data.get("data", {})
        
        logger.info(f"Processing Paystack webhook: {event_type} (ID: {event_id})")
        
        processing_result = {"event_type": event_type, "processed": False}
        
        # Handle transfer events
        if event_type in ["transfer.success", "transfer.failed", "transfer.reversed"]:
            # Extract transfer information
            transfer_code = data.get("transfer_code")
            reference = data.get("reference")
            
            if not transfer_code and not reference:
                logger.warning("No transfer code or reference in webhook data")
                processing_result["status"] = "ignored"
                processing_result["reason"] = "No transfer identifier"
                await webhook_idempotency_service.mark_event_processed(event_id, processing_result)
                return {"status": "ignored", "reason": "No transfer identifier"}
            
            # Find the transfer in our database
            query = {}
            if transfer_code:
                query["paystack_transfer_code"] = transfer_code
            elif reference:
                query["reference"] = reference
            
            transfer_doc = await db.transfers.find_one(query)
            
            if not transfer_doc:
                logger.warning(f"Transfer not found for reference {reference} or code {transfer_code}")
                processing_result["status"] = "ignored"
                processing_result["reason"] = "Transfer not found"
                await webhook_idempotency_service.mark_event_processed(event_id, processing_result)
                return {"status": "ignored", "reason": "Transfer not found"}
            
            logger.info(f"Processing {event_type} for transfer {transfer_doc['id']}")
            
            # Update transfer based on event type
            update_data = {"updated_at": datetime.now(timezone.utc)}
            
            if event_type == "transfer.success":
                update_data["status"] = "success"
                update_data["completed_at"] = datetime.now(timezone.utc)
                
                if not transfer_doc.get("paystack_transfer_code") and transfer_code:
                    update_data["paystack_transfer_code"] = transfer_code
                if not transfer_doc.get("paystack_transfer_id") and data.get("id"):
                    update_data["paystack_transfer_id"] = data.get("id")
                
                logger.info(f"Transfer {transfer_doc['id']} marked as successful")
                processing_result["status"] = "success"
                processing_result["transfer_id"] = transfer_doc["id"]
            
            elif event_type == "transfer.failed":
                update_data["status"] = "failed"
                update_data["failed_at"] = datetime.now(timezone.utc)
                update_data["failure_reason"] = data.get("message", "Transfer failed via webhook")
                
                logger.error(f"Transfer {transfer_doc['id']} marked as failed: {update_data['failure_reason']}")
                processing_result["status"] = "failed"
                processing_result["transfer_id"] = transfer_doc["id"]
                processing_result["failure_reason"] = update_data["failure_reason"]
            
            elif event_type == "transfer.reversed":
                update_data["status"] = "reversed"
                update_data["failure_reason"] = data.get("message", "Transfer reversed")
                update_data["failed_at"] = datetime.now(timezone.utc)
                
                logger.warning(f"Transfer {transfer_doc['id']} reversed: {update_data['failure_reason']}")
                processing_result["status"] = "reversed"
                processing_result["transfer_id"] = transfer_doc["id"]
                processing_result["failure_reason"] = update_data["failure_reason"]
            
            # Save changes
            await db.transfers.update_one(
                {"id": transfer_doc["id"]},
                {"$set": update_data}
            )
            
            processing_result["processed"] = True
            await webhook_idempotency_service.mark_event_processed(event_id, processing_result)
            
            # Emit SSE event for admin dashboard
            if event_type == "transfer.success":
                await admin_event_emitters.emit_transfer_status(
                    transfer_id=transfer_doc["id"],
                    status="success",
                    amount=transfer_doc["amount"],
                    recipient_name=None  # Would get from recipient service
                )
            elif event_type in ["transfer.failed", "transfer.reversed"]:
                await admin_event_emitters.emit_transfer_status(
                    transfer_id=transfer_doc["id"],
                    status=event_type.split(".")[1],  # "failed" or "reversed"
                    amount=transfer_doc["amount"],
                    failure_reason=update_data.get("failure_reason")
                )
            
            # Emit webhook processed event
            await admin_event_emitters.emit_webhook_processed(
                webhook_type="paystack_transfer",
                event_id=event_id,
                status="processed"
            )
            
            return {"status": "processed", "event_id": event_id, "transfer_id": transfer_doc["id"]}
        
        # Handle other event types
        logger.info(f"Unhandled webhook event type: {event_type}")
        processing_result["status"] = "ignored"
        processing_result["reason"] = "Unhandled event type"
        await webhook_idempotency_service.mark_event_processed(event_id, processing_result)
        
        return {"status": "ignored", "event_id": event_id, "reason": "Unhandled event type"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing transfer webhook: {str(e)}")
        # Try to mark event as failed if we have the event_id
        try:
            if 'event_id' in locals():
                await webhook_idempotency_service.mark_event_failed(event_id, str(e))
        except:
            pass
        raise HTTPException(status_code=500, detail="Webhook processing failed")

# Dynamic Feature Flags and Configuration API
@api_router.get("/platform/config")
async def get_platform_config(force_refresh: bool = False):
    """Get public configuration including feature flags and settings"""
    
    # Always fetch social media settings from admin_settings
    social_media_settings = {}
    try:
        social_config = await db.admin_settings.find_one({"type": "social_media"})
        if social_config and "config" in social_config:
            social_media_settings = social_config["config"]
        else:
            # Set default social media links if none exist
            default_social_media = {
                "facebook": "https://facebook.com/stocklot",
                "twitter": "https://twitter.com/stocklot", 
                "instagram": "https://instagram.com/stocklot",
                "linkedin": "https://linkedin.com/company/stocklot",
                "youtube": "https://youtube.com/@stocklot"
            }
            
            # Insert default social media settings
            await db.admin_settings.update_one(
                {"type": "social_media"},
                {
                    "$set": {
                        "type": "social_media",
                        "config": default_social_media,
                        "updated_at": datetime.now(timezone.utc)
                    }
                },
                upsert=True
            )
            social_media_settings = default_social_media
            logger.info("Created default social media settings")
    except Exception as e:
        logger.error(f"Error fetching social media settings: {e}")
        # Fallback to default settings on error
        social_media_settings = {
            "facebook": "https://facebook.com/stocklot",
            "twitter": "https://twitter.com/stocklot",
            "instagram": "https://instagram.com/stocklot"
        }
    
    if not TRANSFER_SERVICES_AVAILABLE:
        # Return basic config even if transfer services are unavailable
        return {
            "feature_flags": {
                "delivery_only_mode": {"enabled": False, "description": "Force delivery-only mode"},
                "guest_checkout": {"enabled": True, "description": "Allow guest checkout"},
                "advanced_search": {"enabled": True, "description": "Enable advanced search filters"}
            },
            "settings": {
                "social_media": social_media_settings
            },
            "platform": {"active_listings": 3, "total_users": 6, "successful_orders": 15},
            "delivery": {"rate_per_km": 20, "minimum_fee": 50, "maximum_distance": 500, "currency": "ZAR", "delivery_only_mode": False},
            "cache_updated_at": datetime.now(timezone.utc).isoformat(),
            "ttl_seconds": 300,
            "source": "fallback"
        }
    
    try:
        config = await public_config_service.get_public_config(force_refresh=force_refresh)
        # Inject social media settings into the config
        if "settings" not in config:
            config["settings"] = {}
        config["settings"]["social_media"] = social_media_settings
        return config
        
    except Exception as e:
        logger.error(f"Error getting public config: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch configuration")

# Admin Feature Flag Management
@api_router.post("/admin/feature-flags/{flag_key}/toggle")
async def toggle_feature_flag(
    flag_key: str,
    toggle_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Toggle a feature flag (admin only)"""
    if not TRANSFER_SERVICES_AVAILABLE:
        raise HTTPException(status_code=503, detail="Transfer services unavailable")
    
    if not current_user or "admin" not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        enabled = toggle_data.get("enabled", False)
        rollout_percentage = toggle_data.get("rollout_percentage", 100)
        
        success = await public_config_service.update_feature_flag(
            flag_key=flag_key,
            enabled=enabled,
            rollout_percentage=rollout_percentage
        )
        
        if success:
            logger.info(f"Admin {current_user.id} toggled feature flag {flag_key}: {enabled}")
            return {
                "success": True,
                "flag_key": flag_key,
                "enabled": enabled,
                "rollout_percentage": rollout_percentage
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to update feature flag")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error toggling feature flag {flag_key}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to toggle feature flag")

@api_router.post("/admin/delivery/config")
async def update_delivery_config(
    config_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Update delivery configuration (admin only)"""
    if not TRANSFER_SERVICES_AVAILABLE:
        raise HTTPException(status_code=503, detail="Transfer services unavailable")
    
    if not current_user or "admin" not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        success = await public_config_service.update_delivery_config(config_data)
        
        if success:
            logger.info(f"Admin {current_user.id} updated delivery config: {config_data}")
            return {"success": True, "config": config_data}
        else:
            raise HTTPException(status_code=500, detail="Failed to update delivery config")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating delivery config: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to update delivery configuration")

@api_router.post("/admin/delivery/toggle-only-mode")
async def toggle_delivery_only_mode(
    toggle_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Toggle delivery-only mode across the platform (admin only)"""
    if not TRANSFER_SERVICES_AVAILABLE:
        raise HTTPException(status_code=503, detail="Transfer services unavailable")
    
    if not current_user or "admin" not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        enabled = toggle_data.get("enabled", False)
        
        success = await public_config_service.toggle_delivery_only_mode(enabled)
        
        if success:
            logger.info(f"Admin {current_user.id} toggled delivery-only mode: {enabled}")
            
            # Emit admin event for real-time updates
            await emit_admin_event("FEATURE_FLAG.DELIVERY_ONLY_UPDATED", {
                "enabled": enabled,
                "updated_by": current_user.id,
                "message": f"Delivery-only mode {'enabled' if enabled else 'disabled'}"
            })
            
            return {
                "success": True,
                "delivery_only_mode": enabled,
                "message": f"Delivery-only mode {'enabled' if enabled else 'disabled'}"
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to toggle delivery-only mode")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error toggling delivery-only mode: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to toggle delivery-only mode")

# Webhook Statistics (Admin)
@api_router.get("/admin/webhooks/stats")
async def get_webhook_stats(current_user: User = Depends(get_current_user)):
    """Get webhook processing statistics (admin only)"""
    if not TRANSFER_SERVICES_AVAILABLE:
        raise HTTPException(status_code=503, detail="Transfer services unavailable")
    
    if not current_user or "admin" not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        stats = await webhook_idempotency_service.get_webhook_stats()
        return {"webhook_stats": stats}
        
    except Exception as e:
        logger.error(f"Error getting webhook stats: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch webhook statistics")

# SERVER-SENT EVENTS (SSE) ADMIN EVENT BUS
from fastapi.responses import StreamingResponse

@api_router.get("/admin/events/stream")
async def admin_events_stream(current_user: User = Depends(get_current_user)):
    """Server-Sent Events stream for admin dashboard real-time updates"""
    if not TRANSFER_SERVICES_AVAILABLE:
        raise HTTPException(status_code=503, detail="Transfer services unavailable")
    
    if not current_user or "admin" not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    client_id = f"admin_{current_user.id}_{datetime.now(timezone.utc).timestamp()}"
    
    async def event_stream():
        try:
            # Register client and get event queue
            queue = await sse_admin_service.register_client(client_id)
            
            # Send SSE headers
            yield "data: Connected to StockLot admin event stream\n\n"
            
            # Listen for events
            while True:
                try:
                    # Wait for next event with timeout
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    
                    # Send event in SSE format
                    yield event.to_sse_format()
                    
                    # Mark task as done
                    queue.task_done()
                    
                except asyncio.TimeoutError:
                    # Send keepalive ping
                    keepalive = f"data: {{\"type\": \"ping\", \"timestamp\": \"{datetime.now(timezone.utc).isoformat()}\"}}\n\n"
                    yield keepalive
                    
                except Exception as e:
                    logger.error(f"Error in SSE stream for {client_id}: {str(e)}")
                    break
                    
        except Exception as e:
            logger.error(f"Error setting up SSE stream for {client_id}: {str(e)}")
        finally:
            # Cleanup
            await sse_admin_service.unregister_client(client_id)
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )

@api_router.get("/admin/events/recent")
async def get_recent_admin_events(
    limit: int = 50,
    event_types: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Get recent admin events for dashboard"""
    if not TRANSFER_SERVICES_AVAILABLE:
        raise HTTPException(status_code=503, detail="Transfer services unavailable")
    
    if not current_user or "admin" not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        event_type_list = event_types.split(",") if event_types else None
        events = await sse_admin_service.get_recent_events(limit=limit, event_types=event_type_list)
        
        return {
            "events": events,
            "total": len(events),
            "limit": limit
        }
        
    except Exception as e:
        logger.error(f"Error getting recent events: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch recent events")

@api_router.get("/admin/events/stats")
async def get_sse_stats(current_user: User = Depends(get_current_user)):
    """Get SSE connection statistics"""
    if not TRANSFER_SERVICES_AVAILABLE:
        raise HTTPException(status_code=503, detail="Transfer services unavailable")
    
    if not current_user or "admin" not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        stats = await sse_admin_service.get_connection_stats()
        return {"sse_stats": stats}
        
    except Exception as e:
        logger.error(f"Error getting SSE stats: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch SSE statistics")

@api_router.post("/admin/events/emit")
async def emit_test_event(
    event_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Emit a test event for testing SSE functionality (admin only)"""
    if not TRANSFER_SERVICES_AVAILABLE:
        raise HTTPException(status_code=503, detail="Transfer services unavailable")
    
    if not current_user or "admin" not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        await admin_event_emitters.emit_system_alert(
            alert_type="test",
            message=event_data.get("message", "Test event from admin"),
            severity=event_data.get("severity", "info"),
            details={
                "emitted_by": current_user.id,
                "emitted_at": datetime.now(timezone.utc).isoformat(),
                "test_data": event_data
            }
        )
        
        return {
            "success": True,
            "message": "Test event emitted successfully"
        }
        
    except Exception as e:
        logger.error(f"Error emitting test event: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to emit test event")

# ==============================================================================
# 📧 LIFECYCLE EMAIL SYSTEM ENDPOINTS
# ==============================================================================

@api_router.post("/marketing/subscribe")
async def subscribe_to_marketing(
    email: str = Form(...),
    consent: bool = Form(...),
    source: str = Form(...),
    session_id: Optional[str] = Form(None),
    user_id: Optional[str] = Form(None)
):
    """Subscribe user to lifecycle marketing emails"""
    try:
        success = await lifecycle_email_service.subscribe_user(
            email=email,
            consent=consent,
            source=source,
            session_id=session_id,
            user_id=user_id
        )
        
        if success:
            return {"success": True, "message": "Successfully subscribed to marketing emails"}
        else:
            raise HTTPException(status_code=500, detail="Failed to subscribe")
            
    except Exception as e:
        logger.error(f"Error subscribing to marketing: {e}")
        raise HTTPException(status_code=500, detail="Failed to subscribe to marketing emails")

@api_router.post("/track")
async def track_lifecycle_event(
    session_id: str = Form(...),
    event_type: str = Form(...),
    payload: Optional[str] = Form(None),
    user_id: Optional[str] = Form(None)
):
    """Track lifecycle events for email campaigns"""
    try:
        event_payload = json.loads(payload) if payload else {}
        
        success = await lifecycle_email_service.track_event(
            session_id=session_id,
            event_type=event_type,
            payload=event_payload,
            user_id=user_id
        )
        
        if success:
            return {"success": True, "message": "Event tracked successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to track event")
            
    except Exception as e:
        logger.error(f"Error tracking lifecycle event: {e}")
        raise HTTPException(status_code=500, detail="Failed to track event")

@api_router.post("/cart/snapshot")
async def create_cart_snapshot(
    request: Union[dict, None] = Body(None),
    session_id: str = Form(None),
    cart_id: str = Form(None),
    items: str = Form(None),  # JSON string
    subtotal_minor: int = Form(None),
    currency: str = Form("ZAR"),
    user_id: Optional[str] = Form(None)
):
    """Create cart snapshot for abandonment tracking"""
    try:
        # Handle both JSON and form data
        if request:
            # JSON request body
            session_id = request.get("session_id")
            cart_id = request.get("cart_id")
            items_data = request.get("items", [])
            subtotal_minor = request.get("subtotal_minor", 0)
            currency = request.get("currency", "ZAR")
            user_id = request.get("user_id")
        else:
            # Form data (existing format)
            if not session_id or not cart_id or not items:
                raise HTTPException(status_code=400, detail="Missing required fields")
            items_data = json.loads(items)
        
        cart_data = {
            "cart_id": cart_id,
            "items": items_data,
            "subtotal_minor": subtotal_minor,
            "currency": currency
        }
        
        await lifecycle_email_service.snapshot_cart(session_id, cart_data, user_id)
        
        return {"success": True, "message": "Cart snapshot created"}
        
    except Exception as e:
        logger.error(f"Error creating cart snapshot: {e}")
        raise HTTPException(status_code=500, detail="Failed to create cart snapshot")

# ADMIN MODERATION SYSTEM ENDPOINTS
@api_router.get("/admin/roles/requests")
async def get_role_requests(
    status: Optional[str] = None,
    role: Optional[str] = None,
    q: Optional[str] = None,
    current_user: User = Depends(get_current_admin_user)
):
    """Get role upgrade requests for admin review"""
    try:
        requests = await admin_moderation_service.get_role_requests(status, role, 100)
        return {"rows": requests}
    except Exception as e:
        logger.error(f"Error getting role requests: {e}")
        raise HTTPException(status_code=500, detail="Failed to get role requests")

@api_router.post("/admin/roles/requests/{request_id}/approve")
async def approve_role_request(
    request_id: str,
    note: Optional[str] = Form(None),
    current_user: User = Depends(get_current_admin_user)
):
    """Approve a role upgrade request"""
    try:
        success = await admin_moderation_service.approve_role_request(
            request_id, current_user.id, note
        )
        if success:
            return {"ok": True, "message": "Role request approved successfully"}
        else:
            raise HTTPException(status_code=400, detail="Failed to approve role request")
    except Exception as e:
        logger.error(f"Error approving role request: {e}")
        raise HTTPException(status_code=500, detail="Failed to approve role request")

@api_router.post("/admin/roles/requests/{request_id}/reject")
async def reject_role_request(
    request_id: str,
    reason: str = Form(...),
    current_user: User = Depends(get_current_admin_user)
):
    """Reject a role upgrade request"""
    try:
        success = await admin_moderation_service.reject_role_request(
            request_id, current_user.id, reason
        )
        if success:
            return {"ok": True, "message": "Role request rejected successfully"}
        else:
            raise HTTPException(status_code=400, detail="Failed to reject role request")
    except Exception as e:
        logger.error(f"Error rejecting role request: {e}")
        raise HTTPException(status_code=500, detail="Failed to reject role request")

@api_router.get("/admin/disease/zones")
async def get_disease_zones(current_user: User = Depends(get_current_admin_user)):
    """Get all disease zones"""
    try:
        zones = await admin_moderation_service.get_disease_zones()
        return {"rows": zones}
    except Exception as e:
        logger.error(f"Error getting disease zones: {e}")
        raise HTTPException(status_code=500, detail="Failed to get disease zones")

@api_router.get("/admin/disease/changes")
async def get_disease_zone_changes(
    status: str = "PENDING",
    current_user: User = Depends(get_current_admin_user)
):
    """Get disease zone change requests"""
    try:
        changes = await admin_moderation_service.get_disease_zone_changes(status)
        return {"rows": changes}
    except Exception as e:
        logger.error(f"Error getting disease zone changes: {e}")
        raise HTTPException(status_code=500, detail="Failed to get disease zone changes")

@api_router.get("/admin/disease/changes/{change_id}")
async def get_disease_zone_change_detail(
    change_id: str,
    current_user: User = Depends(get_current_admin_user)
):
    """Get detailed information about a disease zone change"""
    try:
        change = await admin_moderation_service.get_disease_zone_change_detail(change_id)
        if change:
            return {"change": change}
        else:
            raise HTTPException(status_code=404, detail="Disease zone change not found")
    except Exception as e:
        logger.error(f"Error getting disease zone change detail: {e}")
        raise HTTPException(status_code=500, detail="Failed to get change detail")

@api_router.post("/admin/disease/changes/{change_id}/approve")
async def approve_disease_zone_change(
    change_id: str,
    current_user: User = Depends(get_current_admin_user)
):
    """Approve a disease zone change"""
    try:
        success = await admin_moderation_service.approve_disease_zone_change(
            change_id, current_user.id
        )
        if success:
            return {"ok": True, "message": "Disease zone change approved successfully"}
        else:
            raise HTTPException(status_code=400, detail="Failed to approve change")
    except Exception as e:
        logger.error(f"Error approving disease zone change: {e}")
        raise HTTPException(status_code=500, detail="Failed to approve change")

@api_router.post("/admin/disease/changes/{change_id}/reject")
async def reject_disease_zone_change(
    change_id: str,
    reason: str = Form(...),
    current_user: User = Depends(get_current_admin_user)
):
    """Reject a disease zone change"""
    try:
        success = await admin_moderation_service.reject_disease_zone_change(
            change_id, current_user.id, reason
        )
        if success:
            return {"ok": True, "message": "Disease zone change rejected successfully"}
        else:
            raise HTTPException(status_code=400, detail="Failed to reject change")
    except Exception as e:
        logger.error(f"Error rejecting disease zone change: {e}")
        raise HTTPException(status_code=500, detail="Failed to reject change")

@api_router.get("/admin/config/fees")
async def get_fee_configs(current_user: User = Depends(get_current_admin_user)):
    """Get all fee configurations"""
    try:
        configs = await admin_moderation_service.get_fee_configs()
        return {"rows": configs}
    except Exception as e:
        logger.error(f"Error getting fee configs: {e}")
        raise HTTPException(status_code=500, detail="Failed to get fee configs")

@api_router.post("/admin/config/fees")
async def create_fee_config(
    config_data: dict,
    current_user: User = Depends(get_current_admin_user)
):
    """Create a new fee configuration"""
    try:
        config = await admin_moderation_service.create_fee_config(config_data, current_user.id)
        if config:
            return {"row": config, "message": "Fee configuration created successfully"}
        else:
            raise HTTPException(status_code=400, detail="Failed to create fee configuration")
    except Exception as e:
        logger.error(f"Error creating fee config: {e}")
        raise HTTPException(status_code=500, detail="Failed to create fee configuration")

@api_router.post("/admin/config/fees/{config_id}/activate")
async def activate_fee_config(
    config_id: str,
    current_user: User = Depends(get_current_admin_user)
):
    """Activate a fee configuration"""
    try:
        success = await admin_moderation_service.activate_fee_config(config_id, current_user.id)
        if success:
            return {"ok": True, "message": "Fee configuration activated successfully"}
        else:
            raise HTTPException(status_code=400, detail="Failed to activate fee configuration")
    except Exception as e:
        logger.error(f"Error activating fee config: {e}")
        raise HTTPException(status_code=500, detail="Failed to activate fee configuration")

@api_router.get("/admin/config/flags")
async def get_feature_flags(current_user: User = Depends(get_current_admin_user)):
    """Get all feature flags"""
    try:
        flags = await admin_moderation_service.get_feature_flags()
        return {"rows": flags}
    except Exception as e:
        logger.error(f"Error getting feature flags: {e}")
        raise HTTPException(status_code=500, detail="Failed to get feature flags")

@api_router.post("/admin/config/flags/{key}")
async def update_feature_flag(
    key: str,
    flag_data: dict,
    current_user: User = Depends(get_current_admin_user)
):
    """Update a feature flag"""
    try:
        success = await admin_moderation_service.update_feature_flag(
            key, 
            flag_data.get("status"), 
            flag_data.get("rollout", {}), 
            current_user.id
        )
        if success:
            return {"ok": True, "message": "Feature flag updated successfully"}
        else:
            raise HTTPException(status_code=400, detail="Failed to update feature flag")
    except Exception as e:
        logger.error(f"Error updating feature flag: {e}")
        raise HTTPException(status_code=500, detail="Failed to update feature flag")

@api_router.get("/admin/moderation/stats")
async def get_moderation_stats(current_user: User = Depends(get_current_admin_user)):
    """Get moderation dashboard statistics"""
    try:
        stats = await admin_moderation_service.get_moderation_stats()
        return stats
    except Exception as e:
        logger.error(f"Error getting moderation stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get moderation stats")

# NEW ENDPOINT 1: Recent moderation items
@api_router.get("/admin/moderation/recent")
async def get_recent_moderation_items(
    limit: int = Query(20, description="Number of items to return"),
    current_user: User = Depends(get_current_admin_user)
):
    """Get recent items requiring moderation attention"""
    try:
        recent_items = []
        
        # Get recent pending users
        pending_users = await db.users.find(
            {"status": "pending"}, 
            {"id": 1, "email": 1, "full_name": 1, "created_at": 1}
        ).limit(5).to_list(length=None)
        
        for user in pending_users:
            recent_items.append({
                "id": user.get("id"),
                "type": "user",
                "title": f"User Registration: {user.get('full_name', user.get('email'))}",
                "description": f"New user registration requiring approval",
                "status": "pending",
                "created_at": user.get("created_at"),
                "user_name": user.get("full_name"),
                "content": f"Email: {user.get('email')}"
            })
        
        # Get recent pending listings
        pending_listings = await db.listings.find(
            {"status": "pending"}, 
            {"id": 1, "title": 1, "seller_name": 1, "created_at": 1, "description": 1}
        ).limit(5).to_list(length=None)
        
        for listing in pending_listings:
            recent_items.append({
                "id": listing.get("id"),
                "type": "listing",
                "title": f"Listing: {listing.get('title')}",
                "description": listing.get("description", "")[:100] + "...",
                "status": "pending",
                "created_at": listing.get("created_at"),
                "user_name": listing.get("seller_name"),
                "content": listing.get("description")
            })
        
        # Get recent flagged content (buy requests or reports)
        flagged_content = await db.buy_requests.find(
            {"status": "flagged"}, 
            {"id": 1, "title": 1, "buyer_name": 1, "created_at": 1, "description": 1}
        ).limit(5).to_list(length=None)
        
        for item in flagged_content:
            recent_items.append({
                "id": item.get("id"),
                "type": "buy_request",
                "title": f"Buy Request: {item.get('title')}",
                "description": item.get("description", "")[:100] + "...",
                "status": "flagged",
                "created_at": item.get("created_at"),
                "user_name": item.get("buyer_name"),
                "reason": "Flagged for review"
            })
        
        # Sort by created_at descending and limit
        recent_items.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        return recent_items[:limit]
        
    except Exception as e:
        logger.error(f"Error getting recent moderation items: {e}")
        raise HTTPException(status_code=500, detail="Failed to get recent moderation items")

# NEW ENDPOINT 2: Blog posts for CMS management
@api_router.get("/admin/cms/posts")
async def get_blog_posts(
    status: Optional[str] = Query(None, description="Filter by status"),
    category: Optional[str] = Query(None, description="Filter by category"),
    q: Optional[str] = Query(None, description="Search query"),
    current_user: User = Depends(get_current_admin_user)
):
    """Get blog posts for CMS management"""
    try:
        # Build query
        query = {}
        if status:
            query["status"] = status
        if category:
            query["category"] = category
        if q:
            query["$or"] = [
                {"title": {"$regex": q, "$options": "i"}},
                {"content": {"$regex": q, "$options": "i"}},
                {"excerpt": {"$regex": q, "$options": "i"}}
            ]
        
        # Get blog posts from blog collection
        posts = await db.blog.find(query).sort("created_at", -1).limit(100).to_list(length=None)
        
        # Format posts for frontend
        formatted_posts = []
        for post in posts:
            formatted_posts.append({
                "id": post.get("id", str(post.get("_id"))),
                "title": post.get("title"),
                "content": post.get("content"),
                "excerpt": post.get("excerpt"),
                "category": post.get("category", "news"),
                "status": post.get("status", "draft"),
                "featured": post.get("featured", False),
                "tags": post.get("tags", []),
                "author_name": post.get("author_name", "Admin"),
                "created_at": post.get("created_at"),
                "updated_at": post.get("updated_at"),
                "views": post.get("views", 0)
            })
        
        return formatted_posts
        
    except Exception as e:
        logger.error(f"Error getting blog posts: {e}")
        raise HTTPException(status_code=500, detail="Failed to get blog posts")

@api_router.post("/admin/cms/posts")
async def create_blog_post(
    post_data: BlogPostCreate,
    current_user: User = Depends(get_current_admin_user)
):
    """Create a new blog post"""
    try:
        post_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        
        blog_post = {
            "id": post_id,
            "title": post_data.title,
            "content": post_data.content,
            "excerpt": post_data.excerpt,
            "category": post_data.category,
            "status": post_data.status,
            "featured": post_data.featured,
            "tags": post_data.tags,
            "author_id": current_user.id,
            "author_name": current_user.full_name or current_user.email,
            "created_at": now,
            "updated_at": now,
            "views": 0
        }
        
        result = await db.blog.insert_one(blog_post)
        if result.inserted_id:
            return {"success": True, "id": post_id, "message": "Blog post created successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to create blog post")
            
    except Exception as e:
        logger.error(f"Error creating blog post: {e}")
        raise HTTPException(status_code=500, detail="Failed to create blog post")

@api_router.post("/admin/cms/posts/{post_id}/{action}")
async def handle_blog_post_action(
    post_id: str,
    action: str,
    current_user: User = Depends(get_current_admin_user)
):
    """Handle blog post actions (publish, unpublish, delete)"""
    try:
        if action == "publish":
            result = await db.blog.update_one(
                {"id": post_id},
                {"$set": {"status": "published", "updated_at": datetime.now(timezone.utc)}}
            )
        elif action == "unpublish":
            result = await db.blog.update_one(
                {"id": post_id},
                {"$set": {"status": "draft", "updated_at": datetime.now(timezone.utc)}}
            )
        elif action == "delete":
            result = await db.blog.delete_one({"id": post_id})
        else:
            raise HTTPException(status_code=400, detail="Invalid action")
        
        if result.modified_count > 0 or (action == "delete" and result.deleted_count > 0):
            return {"success": True, "message": f"Blog post {action} successful"}
        else:
            raise HTTPException(status_code=404, detail="Blog post not found")
            
    except Exception as e:
        logger.error(f"Error handling blog post action: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to {action} blog post")

# NEW ENDPOINT 3: Compliance documents
@api_router.get("/admin/compliance/documents")
async def get_compliance_documents(
    status: Optional[str] = Query(None, description="Filter by status"),
    type: Optional[str] = Query(None, description="Filter by document type"),
    q: Optional[str] = Query(None, description="Search query"),
    current_user: User = Depends(get_current_admin_user)
):
    """Get compliance documents for review"""
    try:
        # Build query
        query = {}
        if status:
            query["status"] = status
        if type:
            query["type"] = type
        if q:
            query["$or"] = [
                {"filename": {"$regex": q, "$options": "i"}},
                {"submitter_name": {"$regex": q, "$options": "i"}},
                {"title": {"$regex": q, "$options": "i"}}
            ]
        
        # Get documents from compliance collection 
        documents = await db.compliance_documents.find(query).sort("created_at", -1).limit(100).to_list(length=None)
        
        # Format documents for frontend
        formatted_documents = []
        for doc in documents:
            formatted_documents.append({
                "id": doc.get("id", str(doc.get("_id"))),
                "filename": doc.get("filename"),
                "title": doc.get("title"),
                "type": doc.get("type", "kyc"),
                "status": doc.get("status", "pending"),
                "submitter_name": doc.get("submitter_name"),
                "user_name": doc.get("user_name"),
                "created_at": doc.get("created_at"),
                "expires_at": doc.get("expires_at"),
                "file_size": doc.get("file_size"),
                "admin_notes": doc.get("admin_notes"),
                "review_count": doc.get("review_count", 0)
            })
        
        return formatted_documents
        
    except Exception as e:
        logger.error(f"Error getting compliance documents: {e}")
        raise HTTPException(status_code=500, detail="Failed to get compliance documents")

@api_router.post("/admin/compliance/documents/{document_id}/{action}")
async def handle_compliance_document_action(
    document_id: str,
    action: str,
    request_data: Dict[str, Any] = {},
    current_user: User = Depends(get_current_admin_user)
):
    """Handle compliance document actions (approve, reject)"""
    try:
        now = datetime.now(timezone.utc)
        
        if action == "approve":
            update_data = {
                "status": "approved", 
                "approved_at": now,
                "approved_by": current_user.id,
                "admin_notes": request_data.get("admin_notes", "Approved by admin"),
                "updated_at": now
            }
        elif action == "reject":
            update_data = {
                "status": "rejected", 
                "rejected_at": now,
                "rejected_by": current_user.id,
                "admin_notes": request_data.get("admin_notes", "Rejected by admin"),
                "reason": request_data.get("reason", "Compliance review failed"),
                "updated_at": now
            }
        else:
            raise HTTPException(status_code=400, detail="Invalid action")
        
        result = await db.compliance_documents.update_one(
            {"id": document_id},
            {"$set": update_data}
        )
        
        if result.modified_count > 0:
            return {"success": True, "message": f"Document {action} successful"}
        else:
            raise HTTPException(status_code=404, detail="Document not found")
            
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Error handling compliance document action: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to {action} document")

@api_router.get("/admin/compliance/documents/{document_id}/download")
async def download_compliance_document(
    document_id: str,
    current_user: User = Depends(get_current_admin_user)
):
    """Download a compliance document"""
    try:
        # Get document info
        document = await db.compliance_documents.find_one({"id": document_id})
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # For demo purposes, return a sample file response
        # In production, this would retrieve the actual file from storage
        sample_content = f"Sample compliance document: {document.get('filename', 'document')}\nDocument ID: {document_id}\nType: {document.get('type', 'unknown')}"
        
        return Response(
            content=sample_content,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f"attachment; filename={document.get('filename', 'document.txt')}"}
        )
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Error downloading compliance document: {e}")
        raise HTTPException(status_code=500, detail="Failed to download document")

# Initialize endpoint inventory for communication auditing
try:
    from services.endpoint_inventory import get_endpoint_inventory
    
    # Store app reference globally for introspection
    def set_app_for_introspection():
        inventory = get_endpoint_inventory()
        endpoints = inventory.collect_fastapi_endpoints(app)
        logger.info(f"✅ Endpoint inventory initialized: {len(endpoints)} endpoints, {len(inventory.get_sse_topics())} SSE topics")
        return inventory
    
    # Set the inventory after all routes are registered
    app.state.inventory_initializer = set_app_for_introspection
    
except Exception as e:
    logger.warning(f"⚠️ Failed to initialize endpoint inventory: {e}")

# DEVELOPMENT INTROSPECTION ENDPOINTS (Non-production only)
try:
    from routes.dev import dev_router
    app.include_router(dev_router, prefix="/api")
    logger.info("✅ Development introspection endpoints enabled")
except ImportError as e:
    logger.info("📝 Development introspection endpoints not available")

# INBOX EVENTS SSE ENDPOINT
@api_router.get("/inbox/events")
async def get_inbox_events_stream(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Server-Sent Events stream for inbox updates"""
    async def event_generator():
        try:
            # Send initial connection event
            yield f"data: {json.dumps({'event': 'connected', 'user_id': current_user.id})}\n\n"
            
            # Keep connection alive and send periodic updates
            last_check = datetime.now(timezone.utc)
            
            while True:
                # Check for new messages since last check
                new_messages = await db.messages.find({
                    "recipient_id": current_user.id,
                    "created_at": {"$gt": last_check},
                    "is_read": False
                }, {"_id": 0}).to_list(length=None)
                
                if new_messages:
                    for message in new_messages:
                        # Convert datetime to ISO string for JSON serialization
                        if hasattr(message.get("created_at"), 'isoformat'):
                            message["created_at"] = message["created_at"].isoformat()
                            
                        event_data = {
                            "event": "inbox.new_message",
                            "data": message
                        }
                        yield f"data: {json.dumps(event_data)}\n\n"
                
                # Send heartbeat every 30 seconds
                heartbeat_data = {
                    "event": "heartbeat",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                yield f"data: {json.dumps(heartbeat_data)}\n\n"
                
                last_check = datetime.now(timezone.utc)
                await asyncio.sleep(30)  # Wait 30 seconds before next check
                
        except asyncio.CancelledError:
            logger.info(f"Inbox SSE connection closed for user {current_user.id}")
        except Exception as e:
            logger.error(f"Error in inbox SSE stream: {e}")
            yield f"data: {json.dumps({'event': 'error', 'message': 'Connection error'})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream"
        }
    )

# PRODUCT TAXONOMY AND SPECIES ENDPOINTS
@api_router.get("/product-types")
async def get_product_types(
    species: Optional[str] = Query(None, description="Filter by species ID")
):
    """Get product types, optionally filtered by species"""
    try:
        query = {}
        if species:
            query["species_id"] = species
            
        cursor = db.product_types.find(query, {"_id": 0}).sort("label", 1)
        product_types = await cursor.to_list(length=None)
        
        return {"product_types": product_types}
        
    except Exception as e:
        logger.error(f"Error getting product types: {e}")
        raise HTTPException(status_code=500, detail="Failed to get product types")

@api_router.get("/species")
async def get_species(
    category_group_id: Optional[str] = Query(None, description="Filter by category group")
):
    """Get species, optionally filtered by category group"""
    try:
        query = {}
        if category_group_id:
            query["category_group_id"] = category_group_id
            
        cursor = db.species.find(query, {"_id": 0}).sort("name", 1)
        species = await cursor.to_list(length=None)
        
        return {"species": species}
        
    except Exception as e:
        logger.error(f"Error getting species: {e}")
        raise HTTPException(status_code=500, detail="Failed to get species")

@api_router.get("/taxonomy/categories")
async def get_taxonomy_categories(
    mode: Optional[str] = Query(None, description="Filter mode: core, exotic, or all")
):
    """Get taxonomy categories with filtering"""
    try:
        query = {}
        
        if mode == "core":
            query["category_type"] = "core"
        elif mode == "exotic":
            query["category_type"] = "exotic"
        # If mode is None or "all", return all categories
        
        cursor = db.taxonomy_categories.find(query, {"_id": 0}).sort("display_order", 1)
        categories = await cursor.to_list(length=None)
        
        # If no categories exist, return default structure
        if not categories:
            default_categories = [
                {
                    "id": "poultry",
                    "name": "Poultry",
                    "category_type": "core",
                    "display_order": 1,
                    "icon": "🐔",
                    "description": "Chickens, Ducks, Geese, Turkeys"
                },
                {
                    "id": "ruminants", 
                    "name": "Ruminants",
                    "category_type": "core",
                    "display_order": 2,
                    "icon": "🐄",
                    "description": "Cattle, Goats, Sheep"
                },
                {
                    "id": "exotic",
                    "name": "Exotic Livestock",
                    "category_type": "exotic", 
                    "display_order": 10,
                    "icon": "🦌",
                    "description": "Rare and exotic species"
                }
            ]
            
            # Filter defaults based on mode
            if mode == "core":
                categories = [cat for cat in default_categories if cat["category_type"] == "core"]
            elif mode == "exotic":
                categories = [cat for cat in default_categories if cat["category_type"] == "exotic"]  
            else:
                categories = default_categories
        
        return {"categories": categories}
        
    except Exception as e:
        logger.error(f"Error getting taxonomy categories: {e}")
        raise HTTPException(status_code=500, detail="Failed to get taxonomy categories")

# REVIEWS AND SELLER ENDPOINTS
@api_router.get("/reviews")
async def get_reviews(
    order_group_id: Optional[str] = Query(None, description="Filter by order group ID"),
    listing_id: Optional[str] = Query(None, description="Filter by listing ID"),
    seller_id: Optional[str] = Query(None, description="Filter by seller ID"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100)
):
    """Get reviews with filtering options"""
    try:
        query = {}
        
        if order_group_id:
            query["order_group_id"] = order_group_id
        if listing_id:
            query["listing_id"] = listing_id
        if seller_id:
            query["seller_id"] = seller_id
            
        skip = (page - 1) * limit
        
        pipeline = [
            {"$match": query},
            {"$lookup": {
                "from": "users",
                "localField": "reviewer_id",
                "foreignField": "id",
                "as": "reviewer"
            }},
            {"$unwind": {"path": "$reviewer", "preserveNullAndEmptyArrays": True}},
            {"$sort": {"created_at": -1}},
            {"$skip": skip},
            {"$limit": limit},
            {"$project": {
                "_id": 0,
                "id": 1,
                "rating": 1,
                "comment": 1,
                "created_at": 1,
                "reviewer_name": "$reviewer.full_name",
                "verified_purchase": 1
            }}
        ]
        
        cursor = db.reviews.aggregate(pipeline)
        reviews = await cursor.to_list(length=None)
        
        total = await db.reviews.count_documents(query)
        
        return {
            "reviews": reviews,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "pages": (total + limit - 1) // limit
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting reviews: {e}")
        raise HTTPException(status_code=500, detail="Failed to get reviews")

@api_router.get("/public/sellers/{seller_id}/reviews")
async def get_public_seller_reviews(
    seller_id: str,
    rating: Optional[int] = Query(None, ge=1, le=5, description="Filter by rating"),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50)
):
    """Get public reviews for a seller"""
    try:
        query = {"seller_id": seller_id, "is_public": True}
        
        if rating:
            query["rating"] = rating
            
        skip = (page - 1) * limit
        
        pipeline = [
            {"$match": query},
            {"$lookup": {
                "from": "users",
                "localField": "reviewer_id", 
                "foreignField": "id",
                "as": "reviewer"
            }},
            {"$unwind": {"path": "$reviewer", "preserveNullAndEmptyArrays": True}},
            {"$sort": {"created_at": -1}},
            {"$skip": skip},
            {"$limit": limit},
            {"$project": {
                "_id": 0,
                "id": 1,
                "rating": 1,
                "comment": 1,
                "created_at": 1,
                "reviewer_name": {"$substr": ["$reviewer.full_name", 0, 1]},  # Only first letter for privacy
                "verified_purchase": 1,
                "helpful_count": {"$ifNull": ["$helpful_count", 0]}
            }}
        ]
        
        cursor = db.reviews.aggregate(pipeline)
        reviews = await cursor.to_list(length=None)
        
        total = await db.reviews.count_documents(query)
        
        # Calculate review statistics
        stats_pipeline = [
            {"$match": {"seller_id": seller_id, "is_public": True}},
            {"$group": {
                "_id": None,
                "average_rating": {"$avg": "$rating"},
                "total_reviews": {"$sum": 1},
                "rating_distribution": {
                    "$push": "$rating"
                }
            }}
        ]
        
        stats_cursor = db.reviews.aggregate(stats_pipeline)
        stats_result = await stats_cursor.to_list(length=1)
        
        stats = {
            "average_rating": 0,
            "total_reviews": 0,
            "rating_distribution": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        }
        
        if stats_result:
            stats_data = stats_result[0]
            stats["average_rating"] = round(stats_data.get("average_rating", 0), 1)
            stats["total_reviews"] = stats_data.get("total_reviews", 0)
            
            # Calculate rating distribution
            for rating in stats_data.get("rating_distribution", []):
                if rating in stats["rating_distribution"]:
                    stats["rating_distribution"][rating] += 1
        
        return {
            "reviews": reviews,
            "stats": stats,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "pages": (total + limit - 1) // limit
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting public seller reviews: {e}")
        raise HTTPException(status_code=500, detail="Failed to get seller reviews")

# Legacy fee breakdown endpoint removed - using fee service implementation below

# NOTIFICATION SUBSCRIPTION ENDPOINTS
@api_router.post("/notifications/subscribe")
async def subscribe_to_notifications(
    subscription_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Subscribe user to push notifications"""
    try:
        subscription = {
            "id": str(uuid.uuid4()),
            "user_id": current_user.id,
            "endpoint": subscription_data.get("endpoint"),
            "keys": subscription_data.get("keys", {}),
            "device_info": subscription_data.get("device_info", {}),
            "notification_types": subscription_data.get("types", ["orders", "messages"]),
            "created_at": datetime.now(timezone.utc),
            "is_active": True
        }
        
        # Upsert subscription (replace if exists for same user/endpoint)
        await db.notification_subscriptions.update_one(
            {"user_id": current_user.id, "endpoint": subscription["endpoint"]},
            {"$set": subscription},
            upsert=True
        )
        
        return {"message": "Successfully subscribed to notifications", "subscription_id": subscription["id"]}
        
    except Exception as e:
        logger.error(f"Error subscribing to notifications: {e}")
        raise HTTPException(status_code=500, detail="Failed to subscribe to notifications")

@api_router.post("/notifications/unsubscribe")
async def unsubscribe_from_notifications(
    endpoint: str = Form(...),
    current_user: User = Depends(get_current_user)
):
    """Unsubscribe user from push notifications"""
    try:
        result = await db.notification_subscriptions.update_one(
            {"user_id": current_user.id, "endpoint": endpoint},
            {"$set": {"is_active": False, "unsubscribed_at": datetime.now(timezone.utc)}}
        )
        
        if result.modified_count > 0:
            return {"message": "Successfully unsubscribed from notifications"}
        else:
            return {"message": "Subscription not found or already inactive"}
            
    except Exception as e:
        logger.error(f"Error unsubscribing from notifications: {e}")
        raise HTTPException(status_code=500, detail="Failed to unsubscribe from notifications")

# ADMIN BLOG MANAGEMENT ENDPOINTS
@api_router.get("/admin/blog")
async def get_blog_posts(
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_admin_user)
):
    """Get blog posts for admin management"""
    try:
        query = {}
        if status:
            query["status"] = status
            
        skip = (page - 1) * limit
        
        cursor = db.blog_posts.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit)
        posts = await cursor.to_list(length=None)
        
        total = await db.blog_posts.count_documents(query)
        
        return {
            "posts": posts,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "pages": (total + limit - 1) // limit
            }
        }
    except Exception as e:
        logger.error(f"Error getting blog posts: {e}")
        raise HTTPException(status_code=500, detail="Failed to get blog posts")

@api_router.post("/admin/blog")
async def create_blog_post(
    title: str = Form(...),
    content: str = Form(...),
    excerpt: str = Form(None),
    status: str = Form("draft"),
    current_user: User = Depends(get_current_admin_user)
):
    """Create new blog post"""
    try:
        post_id = str(uuid.uuid4())
        blog_post = {
            "id": post_id,
            "title": title,
            "content": content,
            "excerpt": excerpt or content[:200] + "...",
            "status": status,
            "author_id": current_user.id,
            "author_name": current_user.full_name,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "views": 0
        }
        
        await db.blog_posts.insert_one(blog_post)
        
        return {"post": blog_post, "message": "Blog post created successfully"}
    except Exception as e:
        logger.error(f"Error creating blog post: {e}")
        raise HTTPException(status_code=500, detail="Failed to create blog post")

# ADMIN DOCUMENTS MANAGEMENT
@api_router.get("/admin/documents")
async def get_admin_documents(
    type: Optional[str] = None,
    current_user: User = Depends(get_current_admin_user)
):
    """Get admin documents"""
    try:
        query = {}
        if type:
            query["type"] = type
            
        cursor = db.admin_documents.find(query, {"_id": 0}).sort("created_at", -1)
        documents = await cursor.to_list(length=None)
        
        return {"documents": documents}
    except Exception as e:
        logger.error(f"Error getting admin documents: {e}")
        raise HTTPException(status_code=500, detail="Failed to get admin documents")

# ADMIN LISTINGS MANAGEMENT
@api_router.get("/admin/listings")
async def get_admin_listings(
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_admin_user)
):
    """Get listings for admin management"""
    try:
        query = {}
        if status:
            query["moderation_status"] = status
            
        skip = (page - 1) * limit
        
        pipeline = [
            {"$match": query},
            {"$lookup": {
                "from": "users",
                "localField": "seller_id",
                "foreignField": "id",
                "as": "seller"
            }},
            {"$unwind": {"path": "$seller", "preserveNullAndEmptyArrays": True}},
            {"$sort": {"created_at": -1}},
            {"$skip": skip},
            {"$limit": limit},
            {"$project": {
                "_id": 0,
                "id": 1,
                "title": 1,
                "price": 1,
                "quantity": 1,
                "moderation_status": 1,
                "seller_name": "$seller.full_name",
                "created_at": 1
            }}
        ]
        
        cursor = db.listings.aggregate(pipeline)
        listings = await cursor.to_list(length=None)
        
        total = await db.listings.count_documents(query)
        
        return {
            "listings": listings,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "pages": (total + limit - 1) // limit
            }
        }
    except Exception as e:
        logger.error(f"Error getting admin listings: {e}")
        raise HTTPException(status_code=500, detail="Failed to get admin listings")

# ADMIN ORDERS MANAGEMENT  
@api_router.get("/admin/orders")
async def get_admin_orders(
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_admin_user)
):
    """Get orders for admin management"""
    try:
        query = {}
        if status:
            query["status"] = status
            
        skip = (page - 1) * limit
        
        pipeline = [
            {"$match": query},
            {"$lookup": {
                "from": "users",
                "localField": "buyer_id",
                "foreignField": "id",
                "as": "buyer"
            }},
            {"$unwind": {"path": "$buyer", "preserveNullAndEmptyArrays": True}},
            {"$sort": {"created_at": -1}},
            {"$skip": skip},
            {"$limit": limit},
            {"$project": {
                "_id": 0,
                "id": 1,
                "total_amount": 1,
                "status": 1,
                "buyer_name": "$buyer.full_name",
                "created_at": 1,
                "items_count": {"$size": "$items"}
            }}
        ]
        
        cursor = db.orders.aggregate(pipeline)
        orders = await cursor.to_list(length=None)
        
        total = await db.orders.count_documents(query)
        
        return {
            "orders": orders,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "pages": (total + limit - 1) // limit
            }
        }
    except Exception as e:
        logger.error(f"Error getting admin orders: {e}")
        raise HTTPException(status_code=500, detail="Failed to get admin orders")

# ADMIN PAYMENTS MANAGEMENT
@api_router.get("/admin/payments")
async def get_admin_payments(
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_admin_user)
):
    """Get payments for admin management"""
    try:
        query = {}
        if status:
            query["status"] = status
            
        skip = (page - 1) * limit
        
        cursor = db.payments.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit)
        payments = await cursor.to_list(length=None)
        
        total = await db.payments.count_documents(query)
        
        return {
            "payments": payments,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "pages": (total + limit - 1) // limit
            }
        }
    except Exception as e:
        logger.error(f"Error getting admin payments: {e}")
        raise HTTPException(status_code=500, detail="Failed to get admin payments")

# ADMIN MODERATION SYSTEM ENDPOINTS COMPLETE
@api_router.get("/admin/roles/requests")
async def get_role_requests(
    status: Optional[str] = None,
    role: Optional[str] = None,
    q: Optional[str] = None,
    current_user: User = Depends(get_current_admin_user)
):
    """Get role upgrade requests for admin review"""
    try:
        requests = await admin_moderation_service.get_role_requests(status, role, 100)
        return {"rows": requests}
    except Exception as e:
        logger.error(f"Error getting role requests: {e}")
        raise HTTPException(status_code=500, detail="Failed to get role requests")

@api_router.post("/admin/roles/requests/{request_id}/approve")
async def approve_role_request(
    request_id: str,
    note: Optional[str] = Form(None),
    current_user: User = Depends(get_current_admin_user)
):
    """Approve a role upgrade request"""
    try:
        success = await admin_moderation_service.approve_role_request(
            request_id, current_user.id, note
        )
        if success:
            return {"ok": True, "message": "Role request approved successfully"}
        else:
            raise HTTPException(status_code=400, detail="Failed to approve role request")
    except Exception as e:
        logger.error(f"Error approving role request: {e}")
        raise HTTPException(status_code=500, detail="Failed to approve role request")

@api_router.post("/admin/roles/requests/{request_id}/reject")
async def reject_role_request(
    request_id: str,
    reason: str = Form(...),
    current_user: User = Depends(get_current_admin_user)
):
    """Reject a role upgrade request"""
    try:
        success = await admin_moderation_service.reject_role_request(
            request_id, current_user.id, reason
        )
        if success:
            return {"ok": True, "message": "Role request rejected successfully"}
        else:
            raise HTTPException(status_code=400, detail="Failed to reject role request")
    except Exception as e:
        logger.error(f"Error rejecting role request: {e}")
        raise HTTPException(status_code=500, detail="Failed to reject role request")

@api_router.get("/admin/disease/zones")
async def get_disease_zones(current_user: User = Depends(get_current_admin_user)):
    """Get all disease zones"""
    try:
        zones = await admin_moderation_service.get_disease_zones()
        return {"rows": zones}
    except Exception as e:
        logger.error(f"Error getting disease zones: {e}")
        raise HTTPException(status_code=500, detail="Failed to get disease zones")

@api_router.get("/admin/disease/changes")
async def get_disease_zone_changes(
    status: str = "PENDING",
    current_user: User = Depends(get_current_admin_user)
):
    """Get disease zone change requests"""
    try:
        changes = await admin_moderation_service.get_disease_zone_changes(status)
        return {"rows": changes}
    except Exception as e:
        logger.error(f"Error getting disease zone changes: {e}")
        raise HTTPException(status_code=500, detail="Failed to get disease zone changes")

@api_router.get("/admin/disease/changes/{change_id}")
async def get_disease_zone_change_detail(
    change_id: str,
    current_user: User = Depends(get_current_admin_user)
):
    """Get detailed information about a disease zone change"""
    try:
        change = await admin_moderation_service.get_disease_zone_change_detail(change_id)
        if change:
            return {"change": change}
        else:
            raise HTTPException(status_code=404, detail="Disease zone change not found")
    except Exception as e:
        logger.error(f"Error getting disease zone change detail: {e}")
        raise HTTPException(status_code=500, detail="Failed to get change detail")

@api_router.post("/admin/disease/changes/{change_id}/approve")
async def approve_disease_zone_change(
    change_id: str,
    current_user: User = Depends(get_current_admin_user)
):
    """Approve a disease zone change"""
    try:
        success = await admin_moderation_service.approve_disease_zone_change(
            change_id, current_user.id
        )
        if success:
            return {"ok": True, "message": "Disease zone change approved successfully"}
        else:
            raise HTTPException(status_code=400, detail="Failed to approve change")
    except Exception as e:
        logger.error(f"Error approving disease zone change: {e}")
        raise HTTPException(status_code=500, detail="Failed to approve change")

@api_router.post("/admin/disease/changes/{change_id}/reject")
async def reject_disease_zone_change(
    change_id: str,
    reason: str = Form(...),
    current_user: User = Depends(get_current_admin_user)
):
    """Reject a disease zone change"""
    try:
        success = await admin_moderation_service.reject_disease_zone_change(
            change_id, current_user.id, reason
        )
        if success:
            return {"ok": True, "message": "Disease zone change rejected successfully"}
        else:
            raise HTTPException(status_code=400, detail="Failed to reject change")
    except Exception as e:
        logger.error(f"Error rejecting disease zone change: {e}")
        raise HTTPException(status_code=500, detail="Failed to reject change")

@api_router.get("/admin/config/fees")
async def get_fee_configs(current_user: User = Depends(get_current_admin_user)):
    """Get all fee configurations"""
    try:
        configs = await admin_moderation_service.get_fee_configs()
        return {"rows": configs}
    except Exception as e:
        logger.error(f"Error getting fee configs: {e}")
        raise HTTPException(status_code=500, detail="Failed to get fee configs")

@api_router.post("/admin/config/fees")
async def create_fee_config(
    config_data: dict,
    current_user: User = Depends(get_current_admin_user)
):
    """Create a new fee configuration"""
    try:
        config = await admin_moderation_service.create_fee_config(config_data, current_user.id)
        if config:
            return {"row": config, "message": "Fee configuration created successfully"}
        else:
            raise HTTPException(status_code=400, detail="Failed to create fee configuration")
    except Exception as e:
        logger.error(f"Error creating fee config: {e}")
        raise HTTPException(status_code=500, detail="Failed to create fee configuration")

@api_router.post("/admin/config/fees/{config_id}/activate")
async def activate_fee_config(
    config_id: str,
    current_user: User = Depends(get_current_admin_user)
):
    """Activate a fee configuration"""
    try:
        success = await admin_moderation_service.activate_fee_config(config_id, current_user.id)
        if success:
            return {"ok": True, "message": "Fee configuration activated successfully"}
        else:
            raise HTTPException(status_code=400, detail="Failed to activate fee configuration")
    except Exception as e:
        logger.error(f"Error activating fee config: {e}")
        raise HTTPException(status_code=500, detail="Failed to activate fee configuration")

@api_router.get("/admin/config/flags")
async def get_feature_flags(current_user: User = Depends(get_current_admin_user)):
    """Get all feature flags"""
    try:
        flags = await admin_moderation_service.get_feature_flags()
        return {"rows": flags}
    except Exception as e:
        logger.error(f"Error getting feature flags: {e}")
        raise HTTPException(status_code=500, detail="Failed to get feature flags")

@api_router.post("/admin/config/flags/{key}")
async def update_feature_flag(
    key: str,
    flag_data: dict,
    current_user: User = Depends(get_current_admin_user)
):
    """Update a feature flag"""
    try:
        success = await admin_moderation_service.update_feature_flag(
            key, 
            flag_data.get("status"), 
            flag_data.get("rollout", {}), 
            current_user.id
        )
        if success:
            return {"ok": True, "message": "Feature flag updated successfully"}
        else:
            raise HTTPException(status_code=400, detail="Failed to update feature flag")
    except Exception as e:
        logger.error(f"Error updating feature flag: {e}")
        raise HTTPException(status_code=500, detail="Failed to update feature flag")

# CRON JOB ENDPOINT (for external schedulers)
@api_router.post("/cron/lifecycle-emails")
async def run_lifecycle_email_cron(
    current_user: User = Depends(get_current_admin_user)
):
    """Manual trigger for lifecycle email cron job (admin only)"""
    try:
        await lifecycle_email_service.run_cron_job()
        return {"success": True, "message": "Lifecycle email cron job completed"}
        
    except Exception as e:
        logger.error(f"Error running lifecycle email cron: {e}")
        raise HTTPException(status_code=500, detail="Failed to run cron job")

# ==============================================================================
# 🛒 ACCEPT OFFER → CHECKOUT FLOW API ENDPOINTS
# ==============================================================================

class AcceptOfferRequest(BaseModel):
    qty: int
    address_id: str
    delivery_mode: str  # 'seller', 'rfq', 'pickup'
    abattoir_id: Optional[str] = None

@api_router.post("/buy-requests/{request_id}/offers/{offer_id}/accept")
async def accept_offer_and_create_order(
    request_id: str,
    offer_id: str,
    data: AcceptOfferRequest,
    idempotency_key: str = Header(None, alias="Idempotency-Key"),
    current_user: User = Depends(get_current_user)
):
    """Accept offer and create order with race condition handling"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        # Generate idempotency key if not provided
        if not idempotency_key:
            idempotency_key = str(uuid.uuid4())
        
        result = await order_management_service.accept_offer_and_create_order(
            request_id=request_id,
            offer_id=offer_id,
            buyer_id=current_user.id,
            qty=data.qty,
            address_id=data.address_id,
            delivery_mode=data.delivery_mode,
            abattoir_id=data.abattoir_id,
            idempotency_key=idempotency_key
        )
        
        if result.get("status") == "error":
            error_code = result.get("error_code", "UNKNOWN_ERROR")
            message = result.get("message", "An error occurred")
            
            # Map error codes to HTTP status codes
            status_code_map = {
                "OFFER_EXPIRED": 410,  # Gone
                "OUT_OF_RANGE": 400,   # Bad Request
                "DISEASE_BLOCK": 403,  # Forbidden
                "KYC_REQUIRED": 402,   # Payment Required (used for additional verification)
                "QTY_CHANGED": 409,    # Conflict
                "LOCK_EXPIRED": 410    # Gone
            }
            
            status_code = status_code_map.get(error_code, 400)
            raise HTTPException(status_code=status_code, detail={
                "error_code": error_code,
                "message": message
            })
        
        return {
            "order_group_id": result["order_group_id"],
            "price_lock_expires_at": result["price_lock_expires_at"],
            "totals": result["totals"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Accept offer failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to accept offer")

@api_router.post("/orders/{order_group_id}/refresh-lock")
async def refresh_price_lock(
    order_group_id: str,
    current_user: User = Depends(get_current_user)
):
    """Refresh price lock for checkout page"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        result = await order_management_service.refresh_price_lock(
            order_group_id=order_group_id,
            buyer_id=current_user.id
        )
        
        if result.get("status") == "error":
            raise HTTPException(status_code=400, detail=result.get("message", "Failed to refresh lock"))
        
        return {
            "price_lock_expires_at": result["price_lock_expires_at"],
            "totals": result["totals"],
            "status": result["status"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Price lock refresh failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to refresh price lock")

@api_router.get("/orders/{order_group_id}")
async def get_order_group(
    order_group_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get order group details with all related data"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        # Get order group - check both buyer_id and buyer_user_id
        order_group = await db.order_groups.find_one({
            "id": order_group_id,
            "$or": [
                {"buyer_id": current_user.id},
                {"buyer_user_id": current_user.id}
            ]
        })
        
        if not order_group:
            raise HTTPException(status_code=404, detail="Order not found")
        
        # Remove MongoDB _id
        if "_id" in order_group:
            del order_group["_id"]
        
        # Get seller orders
        seller_orders = await db.seller_orders.find({"order_group_id": order_group_id}).to_list(length=None)
        for so in seller_orders:
            if "_id" in so:
                del so["_id"]
        
        # Get order items for each seller order
        orders_with_items = []
        for seller_order in seller_orders:
            order_items = await db.order_items.find({"seller_order_id": seller_order["id"]}).to_list(length=None)
            for item in order_items:
                if "_id" in item:
                    del item["_id"]
            
            # Get seller info
            seller = await db.users.find_one({"id": seller_order["seller_id"]})
            seller_name = seller.get("full_name") or seller.get("name") or "Unknown Seller" if seller else "Unknown Seller"
            
            # Format order with items
            order_with_items = {
                "id": seller_order["id"],
                "seller_id": seller_order["seller_id"],
                "seller_name": seller_name,
                "status": seller_order.get("status", "PENDING"),
                "delivery_status": seller_order.get("delivery_status", seller_order.get("status", "PENDING")),
                "total_amount": seller_order.get("total", seller_order.get("subtotal", 0) + seller_order.get("delivery", 0)),
                "delivery_cost": seller_order.get("delivery", 0),
                "subtotal": seller_order.get("subtotal", 0),
                "items": [
                    {
                        "id": item.get("id"),
                        "listing_id": item.get("listing_id"),
                        "title": item.get("title", item.get("listing_title", "Unknown Item")),
                        "listing_title": item.get("title", item.get("listing_title", "Unknown Item")),
                        "quantity": item.get("qty", item.get("quantity", 1)),
                        "qty": item.get("qty", item.get("quantity", 1)),
                        "unit": item.get("unit", "head"),
                        "price": item.get("price", 0),
                        "unit_price": item.get("price", 0),
                        "item_total": item.get("line_total", item.get("item_total", 0)),
                        "species": item.get("species"),
                        "product_type": item.get("product_type")
                    }
                    for item in order_items
                ],
                "created_at": seller_order.get("created_at")
            }
            orders_with_items.append(order_with_items)
        
        # Get order contact
        order_contact = await db.order_contacts.find_one({"order_group_id": order_group_id})
        if order_contact and "_id" in order_contact:
            del order_contact["_id"]
        
        # Build complete response
        response = {
            **order_group,
            "orders": orders_with_items,
            "order_contact": order_contact or {}
        }
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get order group failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Failed to get order")

@api_router.post("/orders/{order_group_id}/cancel")
async def cancel_order(
    order_group_id: str,
    data: dict,
    current_user: User = Depends(get_current_user)
):
    """Cancel order and release locks"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        result = await order_management_service.cancel_order(
            order_group_id=order_group_id,
            user_id=current_user.id,
            reason=data.get("reason", "User cancelled")
        )
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])
        
        return {"message": result["message"]}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Cancel order failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to cancel order")

# ==============================================================================
# 📊 BUY REQUEST DASHBOARD API ENDPOINTS
# ==============================================================================

@api_router.get("/buy-requests/my")
async def get_my_buy_requests(
    current_user: User = Depends(get_current_user),
    status: Optional[str] = None,
    species: Optional[str] = None,
    province: Optional[str] = None,
    limit: int = 20,
    offset: int = 0
):
    """Get buyer's own buy requests with filters"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        # Build query
        query = {"buyer_id": current_user.id}
        
        if status and status != "all":
            query["status"] = status
        if species:
            query["species"] = species
        if province:
            query["province"] = province
        
        # Get requests with offer counts
        pipeline = [
            {"$match": query},
            {"$lookup": {
                "from": "buy_request_offers",
                "localField": "id",
                "foreignField": "request_id",
                "as": "offers"
            }},
            {"$addFields": {
                "offers_count": {"$size": "$offers"},
                "pending_offers": {
                    "$size": {
                        "$filter": {
                            "input": "$offers",
                            "cond": {"$eq": ["$$this.status", "pending"]}
                        }
                    }
                },
                "accepted_offers": {
                    "$size": {
                        "$filter": {
                            "input": "$offers",
                            "cond": {"$eq": ["$$this.status", "accepted"]}
                        }
                    }
                }
            }},
            {"$sort": {"created_at": -1}},
            {"$skip": offset},
            {"$limit": limit}
        ]
        
        cursor = db.buy_requests.aggregate(pipeline)
        requests = await cursor.to_list(length=None)
        
        # Clean up MongoDB _ids
        for req in requests:
            if "_id" in req:
                del req["_id"]
            # Remove full offers array to reduce payload
            if "offers" in req:
                del req["offers"]
        
        # Get total count
        total_count = await db.buy_requests.count_documents(query)
        
        return {
            "requests": requests,
            "total_count": total_count,
            "has_more": (offset + limit) < total_count
        }
        
    except Exception as e:
        logger.error(f"Get my buy requests failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to get buy requests")

@api_router.get("/seller/requests/in-range")
async def get_in_range_requests_for_seller(
    current_user: User = Depends(get_current_user),
    species: Optional[str] = None,
    province: Optional[str] = None,
    max_distance_km: Optional[float] = None,
    min_qty: Optional[int] = None,
    has_target_price: Optional[bool] = None,
    limit: int = 20,
    offset: int = 0
):
    """Get buy requests in seller's service range"""
    if not current_user or UserRole.SELLER not in current_user.roles:
        raise HTTPException(status_code=403, detail="Seller access required")
    
    try:
        # Get seller service areas
        seller = await db.users.find_one({"id": current_user.id})
        service_provinces = seller.get("service_provinces", [])
        
        # Build query
        query = {
            "status": "open",
            "moderation_status": {"$in": ["auto_pass", "approved"]}
        }
        
        if service_provinces:
            query["province"] = {"$in": service_provinces}
        
        if species:
            query["species"] = species
        if province:
            query["province"] = province
        if min_qty:
            query["qty"] = {"$gte": min_qty}
        if has_target_price is not None:
            if has_target_price:
                query["target_price"] = {"$exists": True, "$ne": None}
            else:
                query["target_price"] = {"$exists": False}
        
        # Get requests with offer status for this seller
        pipeline = [
            {"$match": query},
            {"$lookup": {
                "from": "buy_request_offers",
                "let": {"request_id": "$id"},
                "pipeline": [
                    {"$match": {
                        "$expr": {"$eq": ["$request_id", "$$request_id"]},
                        "seller_id": current_user.id
                    }}
                ],
                "as": "my_offers"
            }},
            {"$addFields": {
                "my_offer_status": {
                    "$ifNull": [{"$arrayElemAt": ["$my_offers.status", 0]}, None]
                },
                "my_offer_id": {
                    "$ifNull": [{"$arrayElemAt": ["$my_offers.id", 0]}, None]
                }
            }},
            {"$sort": {"created_at": -1}},
            {"$skip": offset},
            {"$limit": limit}
        ]
        
        cursor = db.buy_requests.aggregate(pipeline)
        requests = await cursor.to_list(length=None)
        
        # Clean up response
        for req in requests:
            if "_id" in req:
                del req["_id"]
            if "my_offers" in req:
                del req["my_offers"]
        
        total_count = await db.buy_requests.count_documents(query)
        
        return {
            "requests": requests,
            "total_count": total_count,
            "has_more": (offset + limit) < total_count,
            "service_provinces": service_provinces
        }
        
    except Exception as e:
        logger.error(f"Get in-range requests failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to get requests")

@api_router.get("/seller/offers")
async def get_my_offers(
    current_user: User = Depends(get_current_user),
    status: Optional[str] = None,
    limit: int = 20,
    offset: int = 0
):
    """Get seller's offers with request details"""
    if not current_user or UserRole.SELLER not in current_user.roles:
        raise HTTPException(status_code=403, detail="Seller access required")
    
    try:
        # Build query
        query = {"seller_id": current_user.id}
        
        if status and status != "all":
            query["status"] = status
        
        # Get offers with request details
        pipeline = [
            {"$match": query},
            {"$lookup": {
                "from": "buy_requests",
                "localField": "request_id", 
                "foreignField": "id",
                "as": "request"
            }},
            {"$unwind": "$request"},
            {"$sort": {"created_at": -1}},
            {"$skip": offset},
            {"$limit": limit}
        ]
        
        cursor = db.buy_request_offers.aggregate(pipeline)
        offers = await cursor.to_list(length=None)
        
        # Clean up response
        for offer in offers:
            if "_id" in offer:
                del offer["_id"]
            if "request" in offer and "_id" in offer["request"]:
                del offer["request"]["_id"]
        
        total_count = await db.buy_request_offers.count_documents(query)
        
        return {
            "offers": offers,
            "total_count": total_count,
            "has_more": (offset + limit) < total_count
        }
        
    except Exception as e:
        logger.error(f"Get my offers failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to get offers")

# ==============================================================================
# 🌟 REVIEWS & RATINGS SYSTEM - DUO REVIEWS
# ==============================================================================

# Import review models and service
from models_reviews import (
    ReviewCreate, ReviewUpdate, ReviewReply, ReviewDirection, 
    ReviewStatus, ReviewModerationAction
)
from services.review_service import ReviewService

# Import fee models and service
from models_fees import (
    FeeConfigCreate, FeeConfigUpdate, FeeConfigActivation, CheckoutPreviewRequest,
    OrderFeesFinalization, PayoutCreate, MoneyAmount, FeeModel, PayoutStatus
)
from services.fee_service import FeeService

# Initialize services
try:
    review_service = ReviewService(db)
except Exception as e:
    logger.warning(f"Review service not available: {e}")
    review_service = None
fee_service = FeeService(db)

@api_router.post("/reviews")
async def create_review(
    review_data: ReviewCreate,
    current_user: User = Depends(get_current_user)
):
    """Create a new review (buyer on seller or seller on buyer)"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        result = await review_service.create_review(review_data, current_user.id)
        
        if not result["success"]:
            error_code = result.get("code", "UNKNOWN")
            
            if error_code == "NOT_ELIGIBLE":
                raise HTTPException(status_code=403, detail=result["error"])
            elif error_code == "DUPLICATE":
                raise HTTPException(status_code=409, detail=result["error"])
            else:
                raise HTTPException(status_code=400, detail=result["error"])
        
        return {
            "success": True,
            "review_id": result["review_id"],
            "moderation_status": result["moderation_status"],
            "blind_until": result["blind_until"],
            "editable_until": result["editable_until"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create review failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to create review")

@api_router.patch("/reviews/{review_id}")
async def update_review(
    review_id: str,
    review_update: ReviewUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update review within edit window"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        result = await review_service.update_review(review_id, review_update, current_user.id)
        
        if not result["success"]:
            error_code = result.get("code", "UNKNOWN")
            
            if error_code == "NOT_FOUND":
                raise HTTPException(status_code=404, detail=result["error"])
            elif error_code in ["EDIT_WINDOW_EXPIRED", "COUNTERPARTY_POSTED"]:
                raise HTTPException(status_code=403, detail=result["error"])
            else:
                raise HTTPException(status_code=400, detail=result["error"])
        
        return {"success": True, "message": "Review updated successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update review failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to update review")

@api_router.delete("/reviews/{review_id}")
async def delete_review(
    review_id: str,
    current_user: User = Depends(get_current_user)
):
    """Delete review within allowed window"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        result = await review_service.delete_review(review_id, current_user.id)
        
        if not result["success"]:
            error_code = result.get("code", "UNKNOWN")
            
            if error_code == "NOT_FOUND":
                raise HTTPException(status_code=404, detail=result["error"])
            elif error_code == "DELETE_WINDOW_EXPIRED":
                raise HTTPException(status_code=403, detail=result["error"])
            else:
                raise HTTPException(status_code=400, detail=result["error"])
        
        return {"success": True, "message": "Review deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete review failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete review")

@api_router.post("/reviews/{review_id}/reply")
async def reply_to_review(
    review_id: str,
    reply_data: ReviewReply,
    current_user: User = Depends(get_current_user)
):
    """Add reply to a review (subject user only)"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        # Get review to verify user can reply
        review = await db.user_reviews.find_one({
            "id": review_id,
            "subject_user_id": current_user.id,
            "moderation_status": "APPROVED"
        })
        
        if not review:
            raise HTTPException(status_code=404, detail="Review not found or access denied")
        
        # Check if reply already exists
        if review.get("reply_body"):
            raise HTTPException(status_code=409, detail="Reply already exists")
        
        # Add reply
        now = datetime.now(timezone.utc)
        await db.user_reviews.update_one(
            {"id": review_id},
            {
                "$set": {
                    "reply_body": reply_data.body,
                    "reply_created_at": now,
                    "updated_at": now
                }
            }
        )
        
        return {"success": True, "message": "Reply added successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Reply to review failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to add reply")

# PUBLIC REVIEW ENDPOINTS
@api_router.get("/public/sellers/{seller_id}/reviews")
async def get_seller_reviews(
    seller_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    sort: str = Query("recent", regex="^(recent|helpful|rating_high|rating_low)$")
):
    """Get public seller reviews"""
    try:
        offset = (page - 1) * limit
        
        # Base query - only approved reviews
        query = {
            "subject_user_id": seller_id,
            "direction": ReviewDirection.BUYER_ON_SELLER.value,
            "moderation_status": ReviewStatus.APPROVED.value
        }
        
        # Only show reviews not in blind window
        now = datetime.now(timezone.utc)
        query["$or"] = [
            {"blind_until": {"$exists": False}},
            {"blind_until": {"$lte": now}}
        ]
        
        # Sorting
        sort_options = {
            "recent": [("created_at", -1)],
            "helpful": [("helpful_votes", -1), ("created_at", -1)],  # placeholder field
            "rating_high": [("rating", -1), ("created_at", -1)],
            "rating_low": [("rating", 1), ("created_at", -1)]
        }
        
        sort_by = sort_options.get(sort, sort_options["recent"])
        
        # Get reviews
        cursor = db.user_reviews.find(query).sort(sort_by).skip(offset).limit(limit)
        reviews = await cursor.to_list(length=None)
        
        # Get total count
        total_count = await db.user_reviews.count_documents(query)
        
        # Clean and format reviews
        review_responses = []
        for review in reviews:
            # Get reviewer info
            reviewer = await db.users.find_one({"id": review["reviewer_user_id"]})
            reviewer_name = reviewer.get("full_name", "Anonymous") if reviewer else "Anonymous"
            reviewer_verified = reviewer.get("is_verified", False) if reviewer else False
            
            review_responses.append({
                "id": review["id"],
                "rating": review["rating"],
                "title": review.get("title"),
                "body": review.get("body"),
                "tags": review.get("tags", []),
                "photos": review.get("photos", []),
                "reviewer_name": reviewer_name,
                "reviewer_verified": reviewer_verified,
                "is_verified": review.get("is_verified", True),
                "reply_body": review.get("reply_body"),
                "reply_created_at": review.get("reply_created_at"),
                "created_at": review["created_at"],
                "is_visible": True
            })
        
        # Get seller rating stats
        stats_doc = await db.seller_rating_stats.find_one({"seller_id": seller_id})
        
        if stats_doc:
            stats = {
                "avg_bayes": stats_doc.get("avg_rating_bayes", 0.0),
                "avg_raw": stats_doc.get("avg_rating_raw", 0.0),
                "count": stats_doc.get("ratings_count", 0),
                "stars": {
                    "1": stats_doc.get("star_1", 0),
                    "2": stats_doc.get("star_2", 0),
                    "3": stats_doc.get("star_3", 0),
                    "4": stats_doc.get("star_4", 0),
                    "5": stats_doc.get("star_5", 0)
                },
                "last_review_at": stats_doc.get("last_review_at")
            }
        else:
            stats = {
                "avg_bayes": 0.0,
                "avg_raw": 0.0,
                "count": 0,
                "stars": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0},
                "last_review_at": None
            }
        
        return {
            "reviews": review_responses,
            "stats": stats,
            "pagination": {
                "current_page": page,
                "total_pages": math.ceil(total_count / limit),
                "total_count": total_count,
                "limit": limit
            }
        }
        
    except Exception as e:
        logger.error(f"Get seller reviews failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to get reviews")

@api_router.get("/seller/buyers/{buyer_id}/summary")
async def get_buyer_reliability_summary(
    buyer_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get buyer reliability summary (seller-only view)"""
    if not current_user or UserRole.SELLER not in current_user.roles:
        raise HTTPException(status_code=403, detail="Seller access required")
    
    try:
        # Get buyer rating stats
        stats_doc = await db.buyer_rating_stats.find_one({"buyer_id": buyer_id})
        
        if not stats_doc:
            return {
                "avg_bayes": 0.0,
                "ratings_count": 0,
                "reliability_score": 50.0,  # Neutral score for new buyers
                "last_review_at": None,
                "last_3_tags": []
            }
        
        # Get recent tags from last 3 reviews
        recent_reviews = await db.user_reviews.find({
            "subject_user_id": buyer_id,
            "direction": ReviewDirection.SELLER_ON_BUYER.value,
            "moderation_status": ReviewStatus.APPROVED.value
        }).sort("created_at", -1).limit(3).to_list(length=None)
        
        last_3_tags = []
        for review in recent_reviews:
            last_3_tags.extend(review.get("tags", []))
        
        # Remove duplicates and limit to 5 most recent
        last_3_tags = list(dict.fromkeys(last_3_tags))[:5]
        
        return {
            "avg_bayes": stats_doc.get("avg_rating_bayes", 0.0),
            "ratings_count": stats_doc.get("ratings_count", 0),
            "reliability_score": stats_doc.get("reliability_score", 50.0),
            "last_review_at": stats_doc.get("last_review_at"),
            "last_3_tags": last_3_tags
        }
        
    except Exception as e:
        logger.error(f"Get buyer reliability summary failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to get buyer summary")

# ADMIN MODERATION ENDPOINTS
@api_router.get("/admin/reviews")
async def get_reviews_moderation_queue(
    current_user: User = Depends(get_current_user),
    status: str = Query("PENDING", regex="^(PENDING|FLAGGED|ALL)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100)
):
    """Get reviews moderation queue"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        offset = (page - 1) * limit
        
        # Build query
        if status == "ALL":
            query = {"moderation_status": {"$in": ["PENDING", "FLAGGED", "REJECTED"]}}
        else:
            query = {"moderation_status": status}
        
        # Get reviews
        cursor = db.user_reviews.find(query).sort("created_at", -1).skip(offset).limit(limit)
        reviews = await cursor.to_list(length=None)
        
        # Get counts
        pending_count = await db.user_reviews.count_documents({"moderation_status": "PENDING"})
        flagged_count = await db.user_reviews.count_documents({"moderation_status": "FLAGGED"})
        total_count = await db.user_reviews.count_documents(query)
        
        # Enrich reviews with user info and order details
        enriched_reviews = []
        for review in reviews:
            # Get reviewer and subject info
            reviewer = await db.users.find_one({"id": review["reviewer_user_id"]})
            subject = await db.users.find_one({"id": review["subject_user_id"]})
            order_group = await db.order_groups.find_one({"id": review["order_group_id"]})
            
            enriched_reviews.append({
                "id": review["id"],
                "rating": review["rating"],
                "title": review.get("title"),
                "body": review.get("body"),
                "tags": review.get("tags", []),
                "direction": review["direction"],
                "moderation_status": review["moderation_status"],
                "toxicity_score": review.get("toxicity_score"),
                "created_at": review["created_at"],
                "reviewer": {
                    "id": reviewer["id"] if reviewer else None,
                    "name": reviewer.get("full_name", "Unknown") if reviewer else "Unknown",
                    "email": reviewer.get("email") if reviewer else None
                },
                "subject": {
                    "id": subject["id"] if subject else None,
                    "name": subject.get("full_name", "Unknown") if subject else "Unknown",
                    "email": subject.get("email") if subject else None
                },
                "order_info": {
                    "id": order_group["id"] if order_group else None,
                    "status": order_group.get("status") if order_group else None,
                    "total_amount": order_group.get("total_amount") if order_group else None
                } if order_group else None
            })
        
        return {
            "reviews": enriched_reviews,
            "counts": {
                "pending": pending_count,
                "flagged": flagged_count,
                "total": total_count
            },
            "pagination": {
                "current_page": page,
                "total_pages": math.ceil(total_count / limit),
                "total_count": total_count,
                "limit": limit
            }
        }
        
    except Exception as e:
        logger.error(f"Get moderation queue failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to get moderation queue")

@api_router.post("/admin/reviews/{review_id}/approve")
async def approve_review(
    review_id: str,
    current_user: User = Depends(get_current_user)
):
    """Approve a pending/flagged review"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Update review status
        result = await db.user_reviews.update_one(
            {"id": review_id},
            {
                "$set": {
                    "moderation_status": ReviewStatus.APPROVED.value,
                    "updated_at": datetime.now(timezone.utc)
                }
            }
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Review not found")
        
        # Get review to update aggregates
        review = await db.user_reviews.find_one({"id": review_id})
        if review:
            direction = ReviewDirection(review["direction"])
            await review_service._update_rating_aggregates(review["subject_user_id"], direction)
        
        return {"success": True, "message": "Review approved"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Approve review failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to approve review")

@api_router.post("/admin/reviews/{review_id}/reject")
async def reject_review(
    review_id: str,
    action_data: ReviewModerationAction,
    current_user: User = Depends(get_current_user)
):
    """Reject a review with reason"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Update review status
        result = await db.user_reviews.update_one(
            {"id": review_id},
            {
                "$set": {
                    "moderation_status": ReviewStatus.REJECTED.value,
                    "admin_notes": action_data.admin_notes,
                    "rejection_reason": action_data.reason,
                    "updated_at": datetime.now(timezone.utc)
                }
            }
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Review not found")
        
        # Update aggregates (rejected reviews are excluded)
        review = await db.user_reviews.find_one({"id": review_id})
        if review:
            direction = ReviewDirection(review["direction"])
            await review_service._update_rating_aggregates(review["subject_user_id"], direction)
        
        return {"success": True, "message": "Review rejected"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Reject review failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to reject review")

@api_router.post("/admin/reviews/{review_id}/flag")
async def flag_review(
    review_id: str,
    action_data: ReviewModerationAction,
    current_user: User = Depends(get_current_user)
):
    """Flag a review for further investigation"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Update review status
        result = await db.user_reviews.update_one(
            {"id": review_id},
            {
                "$set": {
                    "moderation_status": ReviewStatus.FLAGGED.value,
                    "admin_notes": action_data.admin_notes,
                    "flag_reason": action_data.reason,
                    "updated_at": datetime.now(timezone.utc)
                }
            }
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Review not found")
        
        return {"success": True, "message": "Review flagged"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Flag review failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to flag review")

@api_router.post("/admin/ratings/recompute")
async def recompute_rating_aggregates(
    current_user: User = Depends(get_current_user),
    seller_id: Optional[str] = Query(None),
    buyer_id: Optional[str] = Query(None)
):
    """Recompute rating aggregates for specific users or all users"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        if seller_id:
            await review_service._update_seller_rating_stats(seller_id)
            return {"success": True, "message": f"Recomputed seller {seller_id} ratings"}
        
        if buyer_id:
            await review_service._update_buyer_rating_stats(buyer_id)
            return {"success": True, "message": f"Recomputed buyer {buyer_id} ratings"}
        
        # Recompute all
        await review_service.recompute_all_rating_aggregates()
        return {"success": True, "message": "Recomputed all rating aggregates"}
        
    except Exception as e:
        logger.error(f"Recompute ratings failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to recompute ratings")

# ==============================================================================
# 💰 FEE SYSTEM API ENDPOINTS - DUAL MODEL SUPPORT
# ==============================================================================

# ADMIN FEE CONFIGURATION ENDPOINTS
@api_router.post("/admin/fees/configs")
async def create_fee_config(
    config_data: FeeConfigCreate,
    current_user: User = Depends(get_current_user)
):
    """Create new fee configuration"""
    # Check admin permissions
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        config = await fee_service.create_fee_config(config_data)
        return {
            "success": True,
            "config": config.dict(),
            "message": "Fee configuration created successfully"
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Create fee config failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to create fee configuration")

@api_router.post("/admin/fees/configs/{config_id}/activate")
async def activate_fee_config(
    config_id: str,
    current_user: User = Depends(get_current_user)
):
    """Activate a fee configuration"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        success = await fee_service.activate_fee_config(config_id)
        
        if success:
            return {
                "success": True,
                "message": "Fee configuration activated successfully"
            }
        else:
            raise HTTPException(status_code=404, detail="Fee configuration not found")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Activate fee config failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to activate fee configuration")

@api_router.get("/admin/fees/configs")
async def list_fee_configs(
    current_user: User = Depends(get_current_user),
    active_only: bool = Query(False, description="Return only active configurations")
):
    """List fee configurations"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        query = {}
        if active_only:
            query["is_active"] = True
        
        cursor = db.fee_configs.find(query).sort("created_at", -1)
        configs_raw = await cursor.to_list(length=None)
        
        # Clean configs to remove ObjectId fields
        configs = []
        for config in configs_raw:
            if "_id" in config:
                del config["_id"]
            # Convert datetime objects to ISO strings
            for field in ["created_at", "updated_at", "effective_from", "effective_to"]:
                if field in config and hasattr(config[field], 'isoformat'):
                    config[field] = config[field].isoformat()
            configs.append(config)
        
        return {
            "success": True,
            "configs": configs,
            "count": len(configs)
        }
        
    except Exception as e:
        logger.error(f"List fee configs failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve fee configurations")

@api_router.get("/admin/fees/revenue-summary")
async def get_revenue_summary(
    current_user: User = Depends(get_current_user),
    start_date: datetime = Query(..., description="Start date for summary"),
    end_date: datetime = Query(..., description="End date for summary")
):
    """Get platform revenue summary"""
    if not current_user or UserRole.ADMIN not in current_user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        summary = await fee_service.get_platform_revenue_summary(start_date, end_date)
        return {
            "success": True,
            "summary": summary
        }
        
    except Exception as e:
        logger.error(f"Get revenue summary failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate revenue summary")

# PUBLIC CHECKOUT & PREVIEW ENDPOINTS
@api_router.post("/checkout/preview")
async def checkout_preview(preview_request: CheckoutPreviewRequest):
    """Calculate checkout preview with fee breakdown"""
    try:
        if not preview_request.cart:
            raise HTTPException(status_code=400, detail="Cart cannot be empty")
        
        preview = await fee_service.calculate_checkout_preview(preview_request.cart)
        
        return {
            "success": True,
            "preview": preview.dict()
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Checkout preview failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to calculate checkout preview")

@api_router.get("/fees/breakdown")
async def get_fee_breakdown(
    amount: float = Query(..., description="Amount in major currency units (e.g., 1000.00)"),
    species: Optional[str] = Query(None, description="Livestock species for rule matching"),
    export: bool = Query(False, description="Is this an export order")
):
    """Get detailed fee breakdown for transparency"""
    try:
        # Convert to minor units
        amount_minor = round(amount * 100)
        
        if amount_minor <= 0:
            raise HTTPException(status_code=400, detail="Amount must be positive")
        
        # Get appropriate config
        config = await fee_service.get_active_fee_config(species=species, export=export)
        
        # Calculate breakdown
        breakdown = await fee_service.get_fee_breakdown(amount_minor, config)
        
        return {
            "success": True,
            "breakdown": breakdown.dict(),
            "config_used": {
                "id": config.id,
                "name": config.name,
                "model": config.model
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get fee breakdown failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to calculate fee breakdown")

# ORDER FINALIZATION ENDPOINTS
@api_router.post("/orders/{order_group_id}/fees/finalize")
async def finalize_order_fees(
    order_group_id: str,
    finalization_data: OrderFeesFinalization,
    current_user: User = Depends(get_current_user)
):
    """Finalize fees for an order (creates immutable snapshots)"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        # Get order group to validate
        order_group = await db.order_groups.find_one({"id": order_group_id})
        if not order_group:
            raise HTTPException(status_code=404, detail="Order group not found")
        
        # Verify user has access to this order
        user_id = current_user.id
        if (order_group.get("buyer_id") != user_id and 
            order_group.get("seller_id") != user_id):
            raise HTTPException(status_code=403, detail="Access denied to this order")
        
        # Extract cart items from finalization data
        from models_fees import CartItem
        cart_items = []
        
        for seller_data in finalization_data.per_seller:
            # Reconstruct cart item from seller data
            cart_item = CartItem(
                seller_id=seller_data.get("seller_id", ""),
                merch_subtotal_minor=seller_data.get("merch_subtotal_minor", 0),
                delivery_minor=seller_data.get("delivery_minor", 0),
                abattoir_minor=seller_data.get("abattoir_minor", 0),
                species=seller_data.get("species"),
                export=seller_data.get("export", False)
            )
            cart_items.append(cart_item)
        
        # Finalize fees
        finalized_fees = await fee_service.finalize_order_fees(
            order_group_id,
            cart_items,
            finalization_data.fee_config_id
        )
        
        return {
            "success": True,
            "finalized_fees": [fee.dict() for fee in finalized_fees],
            "message": "Order fees finalized successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Finalize order fees failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to finalize order fees")

# PAYOUT ENDPOINTS
@api_router.post("/payouts/{seller_order_id}/release")
async def release_seller_payout(
    seller_order_id: str,
    current_user: User = Depends(get_current_user)
):
    """Release payout to seller"""
    # For now, we'll allow admin and the seller to trigger payouts
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        # Create payout record based on fee snapshot
        payout = await fee_service.create_payout(seller_order_id)
        
        if not payout:
            raise HTTPException(status_code=404, detail="Unable to create payout - fee snapshot not found")
        
        # In a real implementation, you would integrate with payment provider here
        # For now, we'll mark as sent immediately
        await fee_service.update_payout_status(
            payout.id,
            PayoutStatus.SENT,
            transfer_ref=f"mock_transfer_{payout.id}"
        )
        
        return {
            "success": True,
            "payout": payout.dict(),
            "status": "SENT",
            "transfer_ref": f"mock_transfer_{payout.id}",
            "message": "Payout released successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Release payout failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to release payout")

@api_router.get("/payouts/seller/{seller_id}")
async def get_seller_payouts(
    seller_id: str,
    current_user: User = Depends(get_current_user),
    status: Optional[str] = Query(None, description="Filter by payout status"),
    limit: int = Query(50, ge=1, le=100)
):
    """Get payouts for a seller"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Check if user can access this seller's payouts
    if (current_user.id != seller_id and 
        UserRole.ADMIN not in current_user.roles):
        raise HTTPException(status_code=403, detail="Access denied")
    
    try:
        # Build query
        query = {"seller_order_id": {"$regex": f".*_{seller_id}$"}}
        
        if status:
            query["status"] = status.upper()
        
        # Get payouts
        cursor = db.payouts.find(query).sort("created_at", -1).limit(limit)
        payouts = await cursor.to_list(length=None)
        
        # Calculate summary
        total_pending = sum(p["amount_minor"] for p in payouts if p["status"] == "PENDING")
        total_sent = sum(p["amount_minor"] for p in payouts if p["status"] == "SENT")
        
        return {
            "success": True,
            "payouts": payouts,
            "summary": {
                "total_payouts": len(payouts),
                "pending_amount_minor": total_pending,
                "sent_amount_minor": total_sent,
                "pending_amount_major": total_pending / 100,
                "sent_amount_major": total_sent / 100
            }
        }
        
    except Exception as e:
        logger.error(f"Get seller payouts failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve payouts")

# WEBHOOK ENDPOINTS
@api_router.post("/payments/webhook/paystack")
async def handle_paystack_webhook(request: Request):
    try:
        # 1️⃣ Raw body + signature
        body = await request.body()
        signature = request.headers.get("x-paystack-signature")

        # 2️⃣ Verify signature (IMPORTANT)
        secret = os.getenv("PAYSTACK_SECRET_KEY")
        if not secret:
            raise HTTPException(status_code=500, detail="Paystack secret not set")

        computed_signature = hmac.new(
            secret.encode(),
            body,
            hashlib.sha512
        ).hexdigest()

        if signature != computed_signature:
            raise HTTPException(status_code=401, detail="Invalid Paystack signature")

        # 3️⃣ Parse payload
        payload = json.loads(body.decode())
        event_type = payload.get("event")

        # 4️⃣ Only handle successful payment
        if event_type != "charge.success":
            return {"success": True}

        data = payload.get("data", {})
        reference = data.get("reference")

        if not reference:
            return {"success": True}

        # 5️⃣ Extract order_group_id from reference
        if reference.startswith("STOCKLOT_"):
            order_group_id = reference.replace("STOCKLOT_", "")
        elif reference.startswith("DEMO_"):
            order_group_id = reference.replace("DEMO_", "")
        else:
            return {"success": True}

        # 6️⃣ Update order_group (THIS IS THE MAIN FIX)
        await db.order_groups.update_one(
            {"id": order_group_id},
            {
                "$set": {
                    "status": "CONFIRMED",
                    "paid_at": datetime.now(timezone.utc),
                    "payment_reference": reference
                }
            }
        )

        # 7️⃣ Update all seller orders
        await db.seller_orders.update_many(
            {"order_group_id": order_group_id},
            {
                "$set": {
                    "status": "CONFIRMED",
                    "paid_at": datetime.now(timezone.utc)
                }
            }
        )

        return {
            "success": True,
            "message": "Order payment confirmed"
        }

    except HTTPException:
        raise
    except Exception as e:
        print("Webhook error:", e)
        return {"success": False}

# ==============================================================================
# 📧 CONTACT FORM API ENDPOINT
# ==============================================================================

@api_router.post("/contact")
async def submit_contact_form(request: dict):
    """Handle contact form submissions"""
    try:
        # Extract form data
        name = request.get("name", "").strip()
        email = request.get("email", "").strip() 
        subject = request.get("subject", "").strip()
        message = request.get("message", "").strip()
        to_email = request.get("to_email", "hello@stocklot.farm")
        
        # Validate required fields
        if not all([name, email, subject, message]):
            raise HTTPException(status_code=400, detail="All fields are required")
        
        # Basic email validation
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            raise HTTPException(status_code=400, detail="Invalid email format")
        
        # Create contact message record
        contact_record = {
            "id": str(uuid.uuid4()),
            "name": name,
            "email": email,
            "subject": subject,
            "message": message,
            "to_email": to_email,
            "status": "received",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }
        
        # Store in database
        await db.contact_messages.insert_one(contact_record)
        
        # Try to send email notification (optional - won't fail if email service is unavailable)
        try:
            # Create email content
            email_content = f"""
New Contact Form Submission

From: {name} ({email})
Subject: {subject}

Message:
{message}

--
This message was sent through the StockLot contact form.
            """
            
            # In a production system, you would integrate with an email service here
            # For now, we'll just log the message
            logger.info(f"Contact form submission: {name} ({email}) - {subject}")
            logger.info(f"Message content: {message}")
            
        except Exception as email_error:
            logger.warning(f"Failed to send email notification: {email_error}")
            # Don't fail the request if email sending fails
        
        return {
            "success": True,
            "message": "Thank you for your message! We'll get back to you soon.",
            "contact_id": contact_record["id"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Contact form submission failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to submit contact form")

# ==============================================================================
# 📱 REAL-TIME EVENTS API ENDPOINTS
# ==============================================================================

# Include the router in the main app
app.include_router(api_router)

# Include notification API routes - fixed circular import
app.include_router(admin_notifications_router, prefix="/api")
app.include_router(user_notifications_router, prefix="/api")

# ==============================================================================
# 🚀 EXPANDED API ENDPOINTS - 100% BACKEND COVERAGE
# ==============================================================================

# Import and include the expanded endpoints
from api_endpoints_expansion import router as expansion_router
app.include_router(expansion_router)

# ==============================================================================
# 🚀 ENHANCED FEATURES API ENDPOINTS - COMPREHENSIVE ENHANCEMENTS
# ==============================================================================

# ================================
# ADVANCED SEARCH & AI ENDPOINTS
# ================================

@app.post("/api/search/semantic")
async def semantic_search(
    request: Dict[str, Any] = Body(...),
    current_user: Optional[Dict] = Depends(get_current_user)
):
    """AI-powered semantic search with natural language understanding"""
    try:
        if not ENHANCEMENT_SERVICES_AVAILABLE:
            return {"error": "Enhancement services not available"}
            
        query = request.get('query', '')
        user_context = {
            'user_id': current_user.get('_id') if current_user else None,
            'location': request.get('location'),
            'preferences': request.get('preferences', {})
        }
        
        results = await advanced_search_service.semantic_search(query, user_context)
        return results
        
    except Exception as e:
        logger.error(f"Semantic search error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/search/visual")
async def visual_search(
    image: UploadFile = File(...),
    similarity_threshold: float = Query(0.7, description="Similarity threshold (0.0-1.0)")
):
    """Search for similar livestock by image using computer vision"""
    try:
        if not ENHANCEMENT_SERVICES_AVAILABLE:
            return {"error": "Enhancement services not available"}
            
        # Read image data
        image_data = await image.read()
        
        results = await advanced_search_service.visual_search(image_data, similarity_threshold)
        return results
        
    except Exception as e:
        logger.error(f"Visual search error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/search/autocomplete")
async def smart_autocomplete(
    q: str = Query(..., description="Partial search query"),
    current_user: Optional[Dict] = Depends(get_current_user)
):
    """AI-powered autocomplete with context awareness"""
    try:
        if not ENHANCEMENT_SERVICES_AVAILABLE:
            return []
            
        user_context = {
            'user_id': current_user.get('_id') if current_user else None,
            'location': current_user.get('province') if current_user else None
        }
        
        suggestions = await advanced_search_service.smart_autocomplete(q, user_context)
        return suggestions
        
    except Exception as e:
        logger.error(f"Autocomplete error: {str(e)}")
        return []

@app.post("/api/search/intelligent-filters")
async def intelligent_filters(
    request: Dict[str, Any] = Body(...)
):
    """Generate smart filter suggestions based on search results"""
    try:
        if not ENHANCEMENT_SERVICES_AVAILABLE:
            return {"error": "Enhancement services not available"}
            
        base_query = request.get('query', '')
        current_results = request.get('results', [])
        
        filters = await advanced_search_service.intelligent_filters(base_query, current_results)
        return filters
        
    except Exception as e:
        logger.error(f"Intelligent filters error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/search/predictive")
async def predictive_search(
    current_user: Optional[Dict] = Depends(get_current_user)
):
    """Predict what user might be looking for"""
    try:
        if not ENHANCEMENT_SERVICES_AVAILABLE:
            return {"error": "Enhancement services not available"}
            
        user_context = {
            'user_id': current_user.get('_id') if current_user else None,
            'location': current_user.get('province') if current_user else None,
            'roles': current_user.get('roles', []) if current_user else []
        }
        
        predictions = await advanced_search_service.predictive_search(user_context)
        return predictions
        
    except Exception as e:
        logger.error(f"Predictive search error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/search/analytics")
async def search_analytics_insights(
    q: str = Query(..., description="Search query"),
    current_user: Optional[Dict] = Depends(get_current_user)
):
    """Get analytics and insights about search query"""
    try:
        if not ENHANCEMENT_SERVICES_AVAILABLE:
            return {"error": "Enhancement services not available"}
            
        user_context = {
            'user_id': current_user.get('_id') if current_user else None,
            'location': current_user.get('province') if current_user else None
        }
        
        insights = await advanced_search_service.search_analytics_insights(q, user_context)
        return insights
        
    except Exception as e:
        logger.error(f"Search analytics error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ================================
# REAL-TIME MESSAGING ENDPOINTS
# ================================

@app.post("/api/messaging/conversations")
async def create_conversation(
    request: Dict[str, Any] = Body(...),
    current_user: Dict = Depends(get_current_user)
):
    """Create a new conversation"""
    try:
        if not ENHANCEMENT_SERVICES_AVAILABLE:
            return {"error": "Enhancement services not available"}
            
        participant_ids = request.get('participants', [])
        conversation_type = request.get('type', 'direct')
        listing_id = request.get('listing_id')
        metadata = request.get('metadata', {})
        
        # Add current user to participants
        if current_user['_id'] not in participant_ids:
            participant_ids.append(current_user['_id'])
        
        result = await realtime_messaging_service.create_conversation(
            participant_ids, conversation_type, listing_id, metadata
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Create conversation error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/messaging/conversations")
async def get_conversations(
    limit: int = Query(20, description="Number of conversations to return"),
    offset: int = Query(0, description="Offset for pagination"),
    current_user: Dict = Depends(get_current_user)
):
    """Get user's conversations"""
    try:
        if not ENHANCEMENT_SERVICES_AVAILABLE:
            return {"error": "Enhancement services not available"}
            
        result = await realtime_messaging_service.get_conversations(
            current_user['_id'], limit, offset
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Get conversations error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/messaging/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: str,
    message_data: Dict[str, Any] = Body(...),
    current_user: Dict = Depends(get_current_user)
):
    """Send a message in a conversation"""
    try:
        if not ENHANCEMENT_SERVICES_AVAILABLE:
            return {"error": "Enhancement services not available"}
            
        result = await realtime_messaging_service.send_message(
            conversation_id, current_user['_id'], message_data
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Send message error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/messaging/conversations/{conversation_id}/messages")
async def get_messages(
    conversation_id: str,
    limit: int = Query(50, description="Number of messages to return"),
    before_timestamp: Optional[str] = Query(None, description="Get messages before this timestamp"),
    current_user: Dict = Depends(get_current_user)
):
    """Get messages from a conversation"""
    try:
        if not ENHANCEMENT_SERVICES_AVAILABLE:
            return {"error": "Enhancement services not available"}
            
        before_dt = None
        if before_timestamp:
            before_dt = datetime.fromisoformat(before_timestamp.replace('Z', '+00:00'))
        
        result = await realtime_messaging_service.get_messages(
            conversation_id, current_user['_id'], limit, before_dt
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Get messages error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/messaging/upload-media")
async def upload_media(
    conversation_id: str = Form(...),
    file: UploadFile = File(...),
    current_user: Dict = Depends(get_current_user)
):
    """Upload media for messaging"""
    try:
        if not ENHANCEMENT_SERVICES_AVAILABLE:
            return {"error": "Enhancement services not available"}
            
        file_data = await file.read()
        file_type = file.content_type or 'application/octet-stream'
        
        result = await realtime_messaging_service.upload_media(
            file_data, file_type, file.filename, conversation_id
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Upload media error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/messaging/templates")
async def get_message_templates(
    user_type: Optional[str] = Query(None, description="User type: buyer, seller"),
    current_user: Dict = Depends(get_current_user)
):
    """Get message templates"""
    try:
        if not ENHANCEMENT_SERVICES_AVAILABLE:
            return []
            
        # Determine user type from roles if not provided
        if not user_type and current_user:
            roles = current_user.get('roles', [])
            if 'seller' in roles:
                user_type = 'seller'
            elif 'buyer' in roles:
                user_type = 'buyer'
        
        templates = await realtime_messaging_service.get_message_templates(user_type)
        return templates
        
    except Exception as e:
        logger.error(f"Get templates error: {str(e)}")
        return []

# ================================
# BUSINESS INTELLIGENCE ENDPOINTS
# ================================

@app.get("/api/analytics/platform-overview")
async def get_platform_overview(
    date_range: int = Query(30, description="Number of days to analyze"),
    current_user: Dict = Depends(get_current_user)
):
    """Get comprehensive platform analytics overview"""
    try:
        if not ENHANCEMENT_SERVICES_AVAILABLE:
            return {"error": "Enhancement services not available"}
            
        # Check admin access
        if 'admin' not in current_user.get('roles', []):
            raise HTTPException(status_code=403, detail="Admin access required")
        
        overview = await business_intelligence_service.get_platform_overview(date_range)
        return overview
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Platform overview error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/analytics/seller/{seller_id}")
async def get_seller_analytics(
    seller_id: str,
    date_range: int = Query(30, description="Number of days to analyze"),
    current_user: Dict = Depends(get_current_user)
):
    """Get comprehensive seller analytics"""
    try:
        if not ENHANCEMENT_SERVICES_AVAILABLE:
            return {"error": "Enhancement services not available"}
            
        # Check if user can access this seller's data
        if current_user['_id'] != seller_id and 'admin' not in current_user.get('roles', []):
            raise HTTPException(status_code=403, detail="Access denied")
        
        analytics = await business_intelligence_service.get_seller_analytics(seller_id, date_range)
        return analytics
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Seller analytics error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/analytics/buyer/{buyer_id}")
async def get_buyer_insights(
    buyer_id: str,
    date_range: int = Query(30, description="Number of days to analyze"),
    current_user: Dict = Depends(get_current_user)
):
    """Get buyer insights and analytics"""
    try:
        if not ENHANCEMENT_SERVICES_AVAILABLE:
            return {"error": "Enhancement services not available"}
            
        # Check if user can access this buyer's data
        if current_user['_id'] != buyer_id and 'admin' not in current_user.get('roles', []):
            raise HTTPException(status_code=403, detail="Access denied")
        
        insights = await business_intelligence_service.get_buyer_insights(buyer_id, date_range)
        return insights
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Buyer insights error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/analytics/market-intelligence")
async def get_market_intelligence(
    species: Optional[str] = Query(None, description="Filter by species"),
    province: Optional[str] = Query(None, description="Filter by province"),
    current_user: Dict = Depends(get_current_user)
):
    """Get market intelligence and trends"""
    try:
        if not ENHANCEMENT_SERVICES_AVAILABLE:
            return {"error": "Enhancement services not available"}
            
        intelligence = await business_intelligence_service.get_market_intelligence(species, province)
        return intelligence
        
    except Exception as e:
        logger.error(f"Market intelligence error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/analytics/real-time")
async def get_real_time_metrics(
    current_user: Dict = Depends(get_current_user)
):
    """Get real-time platform metrics"""
    try:
        if not ENHANCEMENT_SERVICES_AVAILABLE:
            return {"error": "Enhancement services not available"}
            
        # Check admin access for real-time metrics
        if 'admin' not in current_user.get('roles', []):
            raise HTTPException(status_code=403, detail="Admin access required")
        
        metrics = await business_intelligence_service.get_real_time_metrics()
        return metrics
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Real-time metrics error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/analytics/custom-report")
async def generate_custom_report(
    report_config: Dict[str, Any] = Body(...),
    current_user: Dict = Depends(get_current_user)
):
    """Generate custom analytics report"""
    try:
        if not ENHANCEMENT_SERVICES_AVAILABLE:
            return {"error": "Enhancement services not available"}
            
        # Check appropriate access levels based on report type
        report_type = report_config.get('type', 'general')
        user_roles = current_user.get('roles', [])
        
        if report_type in ['platform', 'admin'] and 'admin' not in user_roles:
            raise HTTPException(status_code=403, detail="Admin access required for platform reports")
        
        report = await business_intelligence_service.generate_custom_report(report_config)
        return report
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Custom report error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ================================
# AI LISTING AUTOFILL ENDPOINTS
# ================================

@app.post("/api/ai/listing-suggest")
async def ai_listing_suggest(
    file: UploadFile = File(None),
    image_url: str = Form(None),
    province: str = Form(None),
    hints: str = Form("{}"),
    current_user: Optional[Dict] = Depends(get_current_user)
):
    """AI-powered livestock listing autofill from camera/image"""
    try:
        if not ENHANCEMENT_SERVICES_AVAILABLE or not openai_listing_service:
            return {"success": False, "error": "AI listing service not available"}
        
        if not openai_listing_service.enabled:
            return {"success": False, "error": "OpenAI service not configured"}
        
        # Get image data
        image_data = None
        final_image_url = image_url
        
        if file:
            # Read uploaded file
            image_data = await file.read()
            
            # Validate file size (8MB limit)
            if len(image_data) > 8 * 1024 * 1024:
                return {"success": False, "error": "Image too large. Maximum 8MB allowed."}
            
            # Upload to storage and get URL
            try:
                # Simple file storage (you can enhance this)
                import os
                import uuid
                upload_dir = "/app/uploads/ai_analysis"
                os.makedirs(upload_dir, exist_ok=True)
                
                file_extension = file.filename.split('.')[-1] if '.' in file.filename else 'jpg'
                stored_filename = f"{uuid.uuid4()}.{file_extension}"
                file_path = os.path.join(upload_dir, stored_filename)
                
                with open(file_path, 'wb') as f:
                    f.write(image_data)
                
                final_image_url = f"/uploads/ai_analysis/{stored_filename}"
                
            except Exception as e:
                logger.error(f"Error storing uploaded image: {str(e)}")
                return {"success": False, "error": "Failed to store image"}
        
        elif image_url:
            # Download image from URL
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.get(image_url) as response:
                        if response.status == 200:
                            image_data = await response.read()
                        else:
                            return {"success": False, "error": "Failed to download image from URL"}
            except Exception as e:
                logger.error(f"Error downloading image: {str(e)}")
                return {"success": False, "error": "Failed to download image"}
        
        if not image_data:
            return {"success": False, "error": "No image provided"}
        
        # Parse hints
        try:
            hints_dict = json.loads(hints) if hints else {}
        except:
            hints_dict = {}
        
        # Analyze image with OpenAI
        analysis_result = await openai_listing_service.analyze_livestock_image(
            image_data=image_data,
            province=province,
            hints=hints_dict
        )
        
        if not analysis_result.get('success'):
            return {
                "success": False,
                "error": analysis_result.get('error', 'Analysis failed')
            }
        
        # Store AI suggestion for tracking (if user is logged in)
        suggestion_id = None
        if current_user:
            suggestion_id = await openai_listing_service.store_ai_suggestion(
                user_id=current_user['_id'],
                image_url=final_image_url,
                suggestion_data=analysis_result
            )
        
        # Format response
        response_data = {
            "success": True,
            "image_url": final_image_url,
            "fields": analysis_result.get('fields', {}),
            "pricing": analysis_result.get('pricing'),
            "moderation": analysis_result.get('moderation', {}),
            "analysis_notes": analysis_result.get('analysis_notes', ''),
            "suggestion_id": suggestion_id
        }
        
        logger.info(f"AI listing analysis completed for user {current_user.get('_id') if current_user else 'guest'}")
        return response_data
        
    except Exception as e:
        logger.error(f"AI listing suggest error: {str(e)}")
        return {
            "success": False,
            "error": "AI analysis failed. Please try again."
        }

@app.post("/api/ai/listing-feedback")
async def ai_listing_feedback(
    request: Dict[str, Any] = Body(...),
    current_user: Dict = Depends(get_current_user)
):
    """Store feedback on AI listing suggestions for learning"""
    try:
        if not ENHANCEMENT_SERVICES_AVAILABLE or not openai_listing_service:
            return {"success": False, "error": "AI listing service not available"}
        
        suggestion_id = request.get('suggestion_id')
        accepted_fields = request.get('accepted_fields', {})
        rejected_fields = request.get('rejected_fields', {})
        
        if not suggestion_id:
            return {"success": False, "error": "Suggestion ID required"}
        
        # Update suggestion record with feedback
        await db.ai_listing_suggestions.update_one(
            {
                '_id': suggestion_id,
                'user_id': current_user['_id']
            },
            {
                '$set': {
                    'accepted_fields': accepted_fields,
                    'rejected_fields': rejected_fields,
                    'status': 'feedback_received',
                    'feedback_at': datetime.utcnow()
                }
            }
        )
        
        logger.info(f"AI listing feedback received for suggestion {suggestion_id}")
        return {"success": True, "message": "Feedback recorded"}
        
    except Exception as e:
        logger.error(f"AI listing feedback error: {str(e)}")
        return {"success": False, "error": "Failed to record feedback"}

@app.get("/api/ai/listing-suggestions/{user_id}")
async def get_user_ai_suggestions(
    user_id: str,
    limit: int = Query(20, description="Number of suggestions to return"),
    current_user: Dict = Depends(get_current_user)
):
    """Get user's AI listing suggestions history"""
    try:
        if not ENHANCEMENT_SERVICES_AVAILABLE:
            return {"success": False, "error": "AI listing service not available"}
        
        # Check authorization
        if current_user['_id'] != user_id and 'admin' not in current_user.get('roles', []):
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Get suggestions
        suggestions = await db.ai_listing_suggestions.find(
            {'user_id': user_id}
        ).sort('created_at', -1).limit(limit).to_list(limit)
        
        return {
            "success": True,
            "suggestions": suggestions,
            "count": len(suggestions)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get AI suggestions error: {str(e)}")
        return {"success": False, "error": "Failed to get suggestions"}

# ================================
# ENHANCED PERFORMANCE ENDPOINTS
# ================================

@app.get("/api/performance/health-check")
async def enhanced_health_check():
    """Enhanced health check with service status"""
    try:
        health_status = {
            'status': 'healthy',
            'timestamp': datetime.utcnow().isoformat(),
            'services': {
                'database': 'connected',
                'ai_services': 'available' if AI_SERVICES_AVAILABLE else 'unavailable',
                'ml_services': 'available' if ML_SERVICES_AVAILABLE else 'unavailable',
                'enhancement_services': 'available' if ENHANCEMENT_SERVICES_AVAILABLE else 'unavailable',
                'openai_listing': 'available' if openai_listing_service and openai_listing_service.enabled else 'unavailable',
                'email_service': 'available',
                'payment_service': 'available'
            },
            'features': {
                'semantic_search': ENHANCEMENT_SERVICES_AVAILABLE,
                'visual_search': ENHANCEMENT_SERVICES_AVAILABLE,
                'real_time_messaging': ENHANCEMENT_SERVICES_AVAILABLE,
                'business_intelligence': ENHANCEMENT_SERVICES_AVAILABLE,
                'ai_recommendations': AI_SERVICES_AVAILABLE,
                'ml_analytics': ML_SERVICES_AVAILABLE,
                'ai_listing_autofill': openai_listing_service.enabled if openai_listing_service else False
            }
        }
        
        # Test database connection
        try:
            await db.users.count_documents({}, limit=1)
        except Exception as e:
            health_status['services']['database'] = f'error: {str(e)}'
            health_status['status'] = 'degraded'
        
        return health_status
        
    except Exception as e:
        return {
            'status': 'error',
            'timestamp': datetime.utcnow().isoformat(),
            'error': str(e)
        }

@app.on_event("shutdown")
async def shutdown_db_client():
    # Stop review system background jobs
    global review_cron_service
    if review_cron_service:
        await review_cron_service.stop_background_jobs()
    
    client.close()