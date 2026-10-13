from database import SessionLocal
from models import Product

db = SessionLocal()

items = [
    ("Chicken Rice", "Rice", 80),
    ("Parota", "Main Course", 25),
    ("Sambar Rice", "Rice", 50),
    ("Chilli Chicken", "Chicken", 100),
    ("Cauliflower Pakoda", "Snacks", 40),
    ("Pani Puri", "Snacks", 30),
    ("Masal Puri", "Snacks", 30),
]

for name, category, price in items:
    existing = db.query(Product).filter(Product.name == name).first()

    if not existing:
        product = Product(
            name=name,
            category=category,
            price=price,
            available=True,
            stock=20
        )
        db.add(product)

db.commit()
db.close()

print("Canteen items added successfully!")