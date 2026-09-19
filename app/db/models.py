from datetime import datetime, date
from sqlalchemy import Column, Integer, Float, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.db.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String(64), primary_key=True, index=True) # LINE User ID
    name = Column(String(100), default="Suphakorn")
    gender = Column(String(10), default="male")
    age = Column(Integer, default=22)
    height_cm = Column(Float, default=174.0)
    weight_kg = Column(Float, default=72.0)
    goal = Column(String(50), default="recomposition")
    daily_target_kcal = Column(Float, default=1950.0)
    target_protein_g = Column(Float, default=145.0)
    target_carbs_g = Column(Float, default=220.0)
    target_fat_g = Column(Float, default=55.0)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    food_logs = relationship("FoodLog", back_populates="user", cascade="all, delete-orphan")
    workout_logs = relationship("WorkoutLog", back_populates="user", cascade="all, delete-orphan")
    exercises = relationship("UserExercise", back_populates="user", cascade="all, delete-orphan")


class FoodLog(Base):
    __tablename__ = "food_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), ForeignKey("users.id"), index=True)
    meal_type = Column(String(20), default="snack") # pre_workout, lunch, dinner, snack
    food_name = Column(String(200), nullable=False)
    portion = Column(String(150), default="1 จาน")
    calories = Column(Float, default=0.0)
    protein = Column(Float, default=0.0)
    carbs = Column(Float, default=0.0)
    fat = Column(Float, default=0.0)
    image_url = Column(Text, nullable=True)
    logged_at = Column(DateTime, default=datetime.now, index=True)

    user = relationship("User", back_populates="food_logs")


class WorkoutLog(Base):
    __tablename__ = "workout_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), ForeignKey("users.id"), index=True)
    workout_type = Column(String(30), default="weights") # weights, cardio, other
    routine_name = Column(String(150), nullable=False)   # Day 1: Push, เดินชัน 40 นาที
    duration_min = Column(Integer, default=60)
    calories_burned = Column(Float, default=300.0)
    details = Column(Text, nullable=True)
    logged_at = Column(DateTime, default=datetime.now, index=True)

    user = relationship("User", back_populates="workout_logs")


class UserExercise(Base):
    __tablename__ = "user_exercises"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), ForeignKey("users.id"), index=True)
    split_id = Column(String(20), nullable=False) # day_1, day_2, day_3, day_4
    name = Column(String(100), nullable=False)
    weight = Column(String(50), default="20 kg")
    target = Column(String(100), default="กล้ามเนื้อ")
    order_num = Column(Integer, default=1)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    user = relationship("User", back_populates="exercises")
