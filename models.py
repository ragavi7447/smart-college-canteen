from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from database import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    category = Column(String)
    price = Column(Float, nullable=False)
    available = Column(Boolean, default=True)
    stock = Column(Integer, default=0)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    bill_no = Column(String, unique=True, nullable=False)
    customer_name = Column(String, nullable=False)
    total = Column(Float, nullable=False)
    payment_method = Column(String, nullable=False)
    payment_status = Column(String, nullable=False, default="PAID")
    order_date = Column(String, nullable=False)

    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    product_name = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)
    amount = Column(Float, nullable=False)

    order = relationship("Order", back_populates="items")