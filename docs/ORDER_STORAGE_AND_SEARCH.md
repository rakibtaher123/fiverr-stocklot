# Order Storage and Search Mechanism

## 📦 Where Orders Are Saved

Orders are stored in **MongoDB** using multiple related collections:

### 1. **`order_groups` Collection** (Main Order Container)
This is the primary collection that groups all items in a single purchase.

**Location in Code:** `backend/server.py` lines 1952-1963, 6183-6193

**Structure:**
```python
order_group = {
    "id": str(uuid.uuid4()),                    # Unique order group ID
    "tracking_number": "TRK1234567890ABCDEF",   # Public tracking number
    "buyer_user_id": "user_id",                 # Buyer's user ID
    "status": "PENDING",                         # Order status
    "currency": "ZAR",                          # Currency
    "grand_total": 1000.00,                     # Total amount
    "items_count": 5,                           # Number of items
    "delivery_total": 50.00,                    # Delivery cost
    "created_at": datetime.now(timezone.utc)    # Creation timestamp
}
```

**Saved via:**
```python
await db.order_groups.insert_one(order_group)
```

### 2. **`seller_orders` Collection** (Individual Seller Orders)
Each order group can contain multiple seller orders (one per seller).

**Location in Code:** `backend/server.py` lines 1982-1992

**Structure:**
```python
seller_order = {
    "id": str(uuid.uuid4()),                    # Unique seller order ID
    "order_group_id": "order_group_id",         # Links to order_groups
    "seller_id": "seller_id",                   # Seller's user ID
    "subtotal": 500.00,                        # Subtotal for this seller
    "delivery": 25.00,                          # Delivery cost
    "total": 525.00,                            # Total for this seller
    "status": "PENDING",                        # Order status
    "created_at": datetime.now(timezone.utc)    # Creation timestamp
}
```

**Saved via:**
```python
await db.seller_orders.insert_one(seller_order)
```

### 3. **`order_items` Collection** (Individual Items)
Each seller order contains multiple items.

**Location in Code:** `backend/server.py` lines 1996-2008

**Structure:**
```python
order_item = {
    "id": str(uuid.uuid4()),                    # Unique item ID
    "seller_order_id": "seller_order_id",       # Links to seller_orders
    "listing_id": "listing_id",                 # Original listing ID
    "title": "Item Title",                      # Item title
    "species": "cattle",                        # Species
    "product_type": "live",                     # Product type
    "unit": "head",                             # Unit of measurement
    "qty": 10,                                  # Quantity
    "price": 50.00,                             # Unit price
    "line_total": 500.00                        # Total for this line
}
```

**Saved via:**
```python
await db.order_items.insert_one(order_item)
```

### 4. **`order_contacts` Collection** (Contact & Shipping Info)
Stores buyer contact and shipping address information.

**Location in Code:** `backend/server.py` lines 1965-1975

**Structure:**
```python
order_contact = {
    "order_group_id": "order_group_id",         # Links to order_groups
    "email": "buyer@example.com",              # Buyer email
    "phone": "+27123456789",                    # Buyer phone
    "full_name": "John Doe",                    # Buyer name
    "address_json": {                           # Shipping address
        "street": "123 Main St",
        "city": "Cape Town",
        "province": "Western Cape",
        "postal_code": "8000",
        "country": "South Africa"
    },
    "kyc_level_required": 1,                    # KYC requirement
    "kyc_checked_at": None                      # KYC check timestamp
}
```

**Saved via:**
```python
await db.order_contacts.insert_one(order_contact)
```

---

## 🔍 How Orders Are Searched

### 1. **Public Order Tracking (By Tracking Number)**

**Endpoint:** `GET /public/orders/track/{tracking_number}`

**Location in Code:** `backend/server.py` lines 6375-6455

**Search Process:**
```python
# Step 1: Find order group by tracking_number
order_group = await db.order_groups.find_one({
    "tracking_number": tracking_number
})

# Step 2: Find all seller orders for this order group
seller_orders = await db.seller_orders.find({
    "order_group_id": order_group["id"]
}).to_list(length=None)

# Step 3: For each seller order, find all items
for seller_order in seller_orders:
    order_items = await db.order_items.find({
        "seller_order_id": seller_order["id"]
    }).to_list(length=None)

# Step 4: Find contact/shipping info
order_contact = await db.order_contacts.find_one({
    "order_group_id": order_group["id"]
})
```

**Search Query:**
```javascript
// MongoDB Query
db.order_groups.findOne({ "tracking_number": "TRK1234567890ABCDEF" })
```

### 2. **Authenticated Order Details (By Order Group ID)**

**Endpoint:** `GET /orders/{order_group_id}`

**Location in Code:** `backend/server.py` lines 17168-17264

**Search Process:**
```python
# Step 1: Find order group (with buyer verification)
order_group = await db.order_groups.find_one({
    "id": order_group_id,
    "$or": [
        {"buyer_id": current_user.id},
        {"buyer_user_id": current_user.id}
    ]
})

# Step 2-4: Same as public tracking (find seller orders, items, contact)
```

**Search Query:**
```javascript
// MongoDB Query
db.order_groups.findOne({
    "id": "order_group_id",
    "$or": [
        {"buyer_id": "user_id"},
        {"buyer_user_id": "user_id"}
    ]
})
```

### 3. **User Orders List**

**Endpoint:** `GET /orders/user`

**Location in Code:** `backend/server.py` lines 2239-2288

**Search Process:**
```python
# Find all orders where user is buyer
buyer_orders = await db.orders.find({
    "buyer_id": current_user.id
}).sort("created_at", -1).to_list(length=None)

# Find all orders where user is seller
seller_orders = await db.orders.find({
    "seller_id": current_user.id
}).sort("created_at", -1).to_list(length=None)
```

---

## 📊 Data Relationships

```
order_groups (1)
    ├── id: "order_group_id"
    ├── tracking_number: "TRK123..."
    └── buyer_user_id: "user_id"
        │
        ├── order_contacts (1:1)
        │   └── order_group_id → order_groups.id
        │
        └── seller_orders (1:many)
            ├── order_group_id → order_groups.id
            └── seller_id: "seller_id"
                │
                └── order_items (1:many)
                    └── seller_order_id → seller_orders.id
```

---

## 🔑 Key Search Fields

### For Public Tracking:
- **Primary:** `tracking_number` (in `order_groups`)
- **Format:** `TRK{timestamp}{random}` (e.g., `TRK1234567890ABCDEF`)

### For Authenticated Access:
- **Primary:** `id` (in `order_groups`)
- **Filter:** `buyer_id` or `buyer_user_id` (for security)

### For User Orders:
- **Buyer Orders:** `buyer_id` (in `orders` or `order_groups`)
- **Seller Orders:** `seller_id` (in `seller_orders`)

---

## 💾 Database Operations Summary

### **Saving Orders:**
1. `db.order_groups.insert_one()` - Main order group
2. `db.order_contacts.insert_one()` - Contact info
3. `db.seller_orders.insert_one()` - Each seller's order
4. `db.order_items.insert_one()` - Each item in order

### **Searching Orders:**
1. `db.order_groups.find_one()` - Find by tracking_number or id
2. `db.seller_orders.find()` - Find by order_group_id
3. `db.order_items.find()` - Find by seller_order_id
4. `db.order_contacts.find_one()` - Find by order_group_id

---

## 🐛 Current Issue in Code

**Line 6389 in `server.py`:**
```python
seller_orders = await db.seller_orders.find({"order_group_id": order_group_id})
```

**Problem:** `order_group_id` variable is not defined. Should use `order_group["id"]`.

**Fix:**
```python
seller_orders = await db.seller_orders.find({"order_group_id": order_group["id"]}).to_list(length=None)
```

