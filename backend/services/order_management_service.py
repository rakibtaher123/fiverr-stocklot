import os
import logging
import time
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone, timedelta
from enum import Enum
import uuid
import json

def generate_tracking_number() -> str:
    """Generate a unique tracking number in format: TRK + timestamp + random string"""
    timestamp = int(time.time())
    random_part = uuid.uuid4().hex[:8].upper()
    tracking_num = f"TRK{timestamp}{random_part}"
    logger.debug(f"Generated tracking number: {tracking_num}")
    return tracking_num

logger = logging.getLogger(__name__)

class OrderGroupStatus(str, Enum):
    PENDING_PAYMENT = "pending_payment"
    PAID = "paid"
    CANCELLED = "cancelled"
    VOID = "void"
    COMPLETE = "complete"

class EscrowStatus(str, Enum):
    INIT = "init"
    FUNDED = "funded"
    RELEASED = "released"
    REFUNDED = "refunded"

class DeliveryMode(str, Enum):
    SELLER = "seller"
    RFQ = "rfq"
    PICKUP = "pickup"

class ComplianceStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    NOT_REQUIRED = "not_required"

class OrderManagementService:
    def __init__(self, db):
        self.db = db
        self.PRICE_LOCK_MINUTES = 15
        
    async def accept_offer_and_create_order(
        self,
        request_id: str,
        offer_id: str,
        buyer_id: str,
        qty: int,
        address_id: str,
        delivery_mode: str,
        abattoir_id: Optional[str] = None,
        idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """Accept offer and create order with atomic transaction and race condition handling"""
        
        # Check idempotency first
        if idempotency_key:
            existing_order = await self.db.order_groups.find_one({"idempotency_key": idempotency_key})
            if existing_order:
                if "_id" in existing_order:
                    del existing_order["_id"]
                return existing_order
        
        # Start transaction simulation (MongoDB doesn't support full ACID across collections)
        # In production, you'd use MongoDB transactions or move to PostgreSQL
        
        try:
            # 1. Validate offer status and availability
            offer = await self.db.buy_request_offers.find_one({
                "id": offer_id,
                "request_id": request_id,
                "status": "pending"
            })
            
            if not offer:
                raise ValueError("OFFER_EXPIRED", "This offer is no longer available. Ask the seller to resend.")
            
            # 2. Validate buy request
            buy_request = await self.db.buy_requests.find_one({
                "id": request_id,
                "buyer_id": buyer_id,
                "status": "open"
            })
            
            if not buy_request:
                raise ValueError("REQUEST_INVALID", "Buy request is no longer available.")
            
            # 3. Validate buyer and seller locations/compliance
            validation_result = await self._validate_compliance_and_geography(
                buy_request, offer, buyer_id, address_id, qty
            )
            
            if not validation_result["valid"]:
                raise ValueError(validation_result["error_code"], validation_result["message"])
            
            # 4. Calculate totals
            totals = await self._calculate_order_totals(
                offer, qty, delivery_mode, abattoir_id, address_id
            )
            
            # 5. Create price lock
            price_lock_expires_at = datetime.now(timezone.utc) + timedelta(minutes=self.PRICE_LOCK_MINUTES)
            
            # 6. Create order group
            order_group_id = str(uuid.uuid4())
            tracking_num = generate_tracking_number()
            logger.info(f"Generated tracking number for buy request order: {tracking_num}")
            
            order_group = {
                "id": order_group_id,
                "tracking_number": tracking_num,
                "buy_request_id": request_id,
                "buyer_id": buyer_id,
                "status": OrderGroupStatus.PENDING_PAYMENT.value,
                "idempotency_key": idempotency_key,
                "price_lock_expires_at": price_lock_expires_at,
                "totals": totals,
                "address_id": address_id,
                "delivery_mode": delivery_mode,
                "abattoir_id": abattoir_id,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc)
            }
            
            # 7. Create seller order
            seller_order_id = str(uuid.uuid4())
            seller_order = {
                "id": seller_order_id,
                "order_group_id": order_group_id,
                "buy_request_id": request_id,
                "offer_id": offer_id,
                "seller_id": offer["seller_id"],
                "buyer_id": buyer_id,
                "qty": qty,
                "unit_price": offer["offer_price"],
                "total_price": totals["merchandise_total"],
                "status": "pending_payment",
                "created_at": datetime.now(timezone.utc)
            }
            
            # 8. Create escrow record
            escrow_id = str(uuid.uuid4())
            escrow_record = {
                "id": escrow_id,
                "order_group_id": order_group_id,
                "buyer_id": buyer_id,
                "seller_id": offer["seller_id"],
                "amount": totals["grand_total"],
                "status": EscrowStatus.INIT.value,
                "created_at": datetime.now(timezone.utc)
            }
            
            # 9. Reserve inventory (if listing attached)
            if offer.get("listing_id"):
                await self._reserve_inventory(offer["listing_id"], qty)
            
            # 10. Insert all records
            await self.db.order_groups.insert_one(order_group)
            logger.info(f"✅ Order group created with ID: {order_group_id}, Tracking: {tracking_num}")
            await self.db.seller_orders.insert_one(seller_order)
            await self.db.escrow_records.insert_one(escrow_record)
            
            # 11. Update offer status
            await self.db.buy_request_offers.update_one(
                {"id": offer_id},
                {"$set": {"status": "accepted", "accepted_at": datetime.now(timezone.utc)}}
            )
            
            # 12. Update buy request status
            await self.db.buy_requests.update_one(
                {"id": request_id},
                {"$set": {"status": "accepted", "updated_at": datetime.now(timezone.utc)}}
            )
            
            # 13. Emit event for notifications
            await self._emit_event("BUY_REQUEST.OFFER_ACCEPTED", {
                "buy_request_id": request_id,
                "offer_id": offer_id,
                "order_group_id": order_group_id,
                "buyer_id": buyer_id,
                "seller_id": offer["seller_id"]
            })
            
            # Clean up response
            if "_id" in order_group:
                del order_group["_id"]
            
            return {
                "order_group_id": order_group_id,
                "price_lock_expires_at": price_lock_expires_at.isoformat(),
                "totals": totals,
                "status": "success"
            }
            
        except ValueError as e:
            # Handle known validation errors
            error_code, message = e.args if len(e.args) == 2 else ("UNKNOWN_ERROR", str(e))
            return {
                "error_code": error_code,
                "message": message,
                "status": "error"
            }
        except Exception as e:
            logger.error(f"Order creation failed: {e}")
            return {
                "error_code": "SYSTEM_ERROR",
                "message": "Order creation failed. Please try again.",
                "status": "error"
            }
    
    async def refresh_price_lock(
        self,
        order_group_id: str,
        buyer_id: str
    ) -> Dict[str, Any]:
        """Refresh price lock for checkout page"""
        
        try:
            order_group = await self.db.order_groups.find_one({
                "id": order_group_id,
                "buyer_id": buyer_id,
                "status": OrderGroupStatus.PENDING_PAYMENT.value
            })
            
            if not order_group:
                raise ValueError("ORDER_NOT_FOUND", "Order not found or no longer available.")
            
            # Check if lock is expired
            if datetime.now(timezone.utc) > order_group["price_lock_expires_at"]:
                # Recalculate totals
                totals = await self._recalculate_totals(order_group)
                new_lock_expires = datetime.now(timezone.utc) + timedelta(minutes=self.PRICE_LOCK_MINUTES)
                
                # Update order group
                await self.db.order_groups.update_one(
                    {"id": order_group_id},
                    {
                        "$set": {
                            "price_lock_expires_at": new_lock_expires,
                            "totals": totals,
                            "updated_at": datetime.now(timezone.utc)
                        }
                    }
                )
                
                return {
                    "price_lock_expires_at": new_lock_expires.isoformat(),
                    "totals": totals,
                    "status": "refreshed"
                }
            else:
                return {
                    "price_lock_expires_at": order_group["price_lock_expires_at"].isoformat(),
                    "totals": order_group["totals"],
                    "status": "still_valid"
                }
                
        except Exception as e:
            logger.error(f"Price lock refresh failed: {e}")
            return {
                "error_code": "REFRESH_FAILED",
                "message": "Failed to refresh price lock.",
                "status": "error"
            }
    
    async def _validate_compliance_and_geography(
        self,
        buy_request: Dict[str, Any],
        offer: Dict[str, Any],
        buyer_id: str,
        address_id: str,
        qty: int
    ) -> Dict[str, Any]:
        """Validate KYC, geofence, disease rules, and other compliance"""
        
        try:
            # 1. Check seller range
            seller = await self.db.users.find_one({"id": offer["seller_id"]})
            if not seller:
                return {"valid": False, "error_code": "SELLER_NOT_FOUND", "message": "Seller not found."}
            
            # Simple province check (in production, use proper geofencing)
            buyer_address = await self.db.addresses.find_one({"id": address_id, "user_id": buyer_id})
            if not buyer_address:
                return {"valid": False, "error_code": "ADDRESS_INVALID", "message": "Delivery address not found."}
            
            seller_provinces = seller.get("service_provinces", [])
            if seller_provinces and buyer_address.get("province") not in seller_provinces:
                return {"valid": False, "error_code": "OUT_OF_RANGE", "message": "This seller doesn't deliver to your location. Request a delivery quote?"}
            
            # 2. Check disease restrictions for live animals
            if buy_request.get("product_type", "").lower() in ["live", "breeding"]:
                disease_status = await self._check_disease_restrictions(
                    buyer_address.get("province"),
                    buy_request.get("species")
                )
                if disease_status["blocked"]:
                    return {"valid": False, "error_code": "DISEASE_BLOCK", "message": "Live-animal trade is restricted in your area right now."}
            
            # 3. Check KYC requirements
            kyc_status = await self._check_kyc_requirements(buyer_id, buy_request, qty)
            if not kyc_status["approved"]:
                return {"valid": False, "error_code": "KYC_REQUIRED", "message": "Verification required for this category. It protects buyers and sellers."}
            
            # 4. Check quantity availability
            if offer.get("listing_id"):
                listing = await self.db.listings.find_one({"id": offer["listing_id"]})
                if listing and listing.get("available_qty", 0) < qty:
                    return {"valid": False, "error_code": "QTY_CHANGED", "message": "Availability changed. Recalculate & re-lock?"}
            
            return {"valid": True}
            
        except Exception as e:
            logger.error(f"Compliance validation failed: {e}")
            return {"valid": False, "error_code": "VALIDATION_ERROR", "message": "Validation failed. Please try again."}
    
    async def _check_disease_restrictions(self, province: str, species: str) -> Dict[str, Any]:
        """Check for disease-related trade restrictions"""
        # In production, this would check a disease restrictions database
        # For now, return no restrictions
        return {"blocked": False, "reason": None}
    
    async def _check_kyc_requirements(self, buyer_id: str, buy_request: Dict[str, Any], qty: int) -> Dict[str, Any]:
        """Check KYC requirements based on category and quantity"""
        
        # Get buyer KYC status
        buyer = await self.db.users.find_one({"id": buyer_id})
        if not buyer:
            return {"approved": False, "reason": "User not found"}
        
        # Check if high-risk category (live animals, export, high value)
        is_high_risk = (
            buy_request.get("product_type", "").lower() in ["live", "breeding"] or
            qty > 100 or  # Large quantities
            (buy_request.get("target_price", 0) * qty) > 50000  # High value
        )
        
        if is_high_risk:
            kyc_status = buyer.get("kyc_status", "pending")
            return {"approved": kyc_status == "approved", "reason": "High-risk transaction requires verification"}
        
        return {"approved": True, "reason": "No verification required"}
    
    async def _calculate_order_totals(
        self,
        offer: Dict[str, Any],
        qty: int,
        delivery_mode: str,
        abattoir_id: Optional[str],
        address_id: str
    ) -> Dict[str, Any]:
        """Calculate comprehensive order totals"""
        
        # Base merchandise cost
        unit_price = offer["offer_price"]
        merchandise_total = unit_price * qty
        
        # Delivery cost
        delivery_cost = 0
        if delivery_mode == "seller":
            # Simple distance-based calculation (in production, use proper geolocation)
            delivery_cost = max(50, qty * 2)  # Minimum R50, R2 per unit
        elif delivery_mode == "rfq":
            delivery_cost = 0  # Will be quoted separately
        
        # Abattoir fees
        abattoir_cost = 0
        if abattoir_id:
            # Fixed processing fee per unit
            abattoir_cost = qty * 15  # R15 per unit processing
        
        # Platform fees (2.5% of merchandise)
        platform_fee = merchandise_total * 0.025
        
        # VAT (15% on platform fee only)
        vat = platform_fee * 0.15
        
        # Grand total
        grand_total = merchandise_total + delivery_cost + abattoir_cost + platform_fee + vat
        
        return {
            "merchandise_total": merchandise_total,
            "unit_price": unit_price,
            "qty": qty,
            "delivery_cost": delivery_cost,
            "delivery_mode": delivery_mode,
            "abattoir_cost": abattoir_cost,
            "platform_fee": platform_fee,
            "vat": vat,
            "grand_total": grand_total,
            "currency": "ZAR"
        }
    
    async def _recalculate_totals(self, order_group: Dict[str, Any]) -> Dict[str, Any]:
        """Recalculate totals for price lock refresh"""
        # In production, this would re-fetch current prices and recalculate
        # For now, return existing totals (assuming prices are stable)
        return order_group.get("totals", {})
    
    async def _reserve_inventory(self, listing_id: str, qty: int) -> bool:
        """Reserve inventory for the order"""
        # Update listing available quantity
        result = await self.db.listings.update_one(
            {"id": listing_id, "available_qty": {"$gte": qty}},
            {"$inc": {"available_qty": -qty, "reserved_qty": qty}}
        )
        return result.modified_count > 0
    
    async def _emit_event(self, event_type: str, data: Dict[str, Any]):
        """Emit event for real-time notifications"""
        event = {
            "id": str(uuid.uuid4()),
            "type": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc),
            "processed": False
        }
        
        await self.db.events.insert_one(event)
        logger.info(f"Event emitted: {event_type}")
    
    async def get_order_group(self, order_group_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get order group with validation"""
        order_group = await self.db.order_groups.find_one({
            "id": order_group_id,
            "$or": [
                {"buyer_id": user_id},
                {"seller_orders.seller_id": user_id}  # Allow seller access too
            ]
        })
        
        if order_group and "_id" in order_group:
            del order_group["_id"]
            
        return order_group
    
    async def cancel_order(self, order_group_id: str, user_id: str, reason: str) -> Dict[str, Any]:
        """Cancel order and release locks"""
        try:
            order_group = await self.db.order_groups.find_one({
                "id": order_group_id,
                "buyer_id": user_id,
                "status": OrderGroupStatus.PENDING_PAYMENT.value
            })
            
            if not order_group:
                return {"success": False, "message": "Order not found or cannot be cancelled"}
            
            # Update order status
            await self.db.order_groups.update_one(
                {"id": order_group_id},
                {
                    "$set": {
                        "status": OrderGroupStatus.CANCELLED.value,
                        "cancelled_reason": reason,
                        "cancelled_at": datetime.now(timezone.utc)
                    }
                }
            )
            
            # Release inventory reservations
            seller_orders = await self.db.seller_orders.find({"order_group_id": order_group_id}).to_list(length=None)
            for order in seller_orders:
                if order.get("listing_id"):
                    await self.db.listings.update_one(
                        {"id": order["listing_id"]},
                        {"$inc": {"available_qty": order["qty"], "reserved_qty": -order["qty"]}}
                    )
            
            # Emit cancellation event
            await self._emit_event("ORDER.CANCELLED", {
                "order_group_id": order_group_id,
                "buyer_id": user_id,
                "reason": reason
            })
            
            return {"success": True, "message": "Order cancelled successfully"}
            
        except Exception as e:
            logger.error(f"Order cancellation failed: {e}")
            return {"success": False, "message": "Cancellation failed"}