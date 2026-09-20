from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, Float, String, DateTime, ForeignKey, Text, JSON,
    UniqueConstraint, CheckConstraint, Boolean, Date, Index,
    false,
)
from sqlalchemy.orm import relationship
from app.db.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String(64), primary_key=True, index=True) # LINE User ID
    name = Column(String(100), nullable=True)
    birth_date = Column(Date, nullable=True)
    gender = Column(String(20), nullable=True)
    age = Column(Integer, nullable=True)
    height_cm = Column(Float, nullable=True)
    weight_kg = Column(Float, nullable=True)
    goal = Column(String(50), nullable=True)
    activity_level = Column(String(30), nullable=True)
    timezone = Column(String(64), nullable=False, default="Asia/Bangkok", server_default="Asia/Bangkok")
    daily_target_kcal = Column(Float, nullable=True)
    target_protein_g = Column(Float, nullable=True)
    target_carbs_g = Column(Float, nullable=True)
    target_fat_g = Column(Float, nullable=True)
    profile_completed = Column(Boolean, nullable=False, default=False, server_default=false())
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    food_logs = relationship("FoodLog", back_populates="user", cascade="all, delete-orphan")
    food_captures = relationship("FoodCapture", back_populates="user", cascade="all, delete-orphan")
    workout_programs = relationship("WorkoutProgram", back_populates="user", cascade="all, delete-orphan")
    workout_sessions = relationship("WorkoutSession", back_populates="user", cascade="all, delete-orphan")
    cardio_presets = relationship("CardioPreset", back_populates="user", cascade="all, delete-orphan")


class FoodLog(Base):
    __tablename__ = "food_logs"
    __table_args__ = (
        CheckConstraint("calories >= 0", name="ck_food_log_calories"),
        CheckConstraint("protein >= 0", name="ck_food_log_protein"),
        CheckConstraint("carbs >= 0", name="ck_food_log_carbs"),
        CheckConstraint("fat >= 0", name="ck_food_log_fat"),
        Index("ix_food_logs_user_logged_at", "user_id", "logged_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), ForeignKey("users.id"), nullable=False, index=True)
    food_name = Column(String(200), nullable=False)
    portion = Column(String(150), default="1 จาน")
    calories = Column(Float, default=0.0, server_default="0", nullable=False)
    protein = Column(Float, default=0.0, server_default="0", nullable=False)
    carbs = Column(Float, default=0.0, server_default="0", nullable=False)
    fat = Column(Float, default=0.0, server_default="0", nullable=False)
    image_url = Column(Text, nullable=True)
    capture_id = Column(Integer, ForeignKey("food_captures.id"), nullable=True, index=True)
    logged_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    user = relationship("User", back_populates="food_logs")
    capture = relationship("FoodCapture", back_populates="food_logs")


class ProgramTemplate(Base):
    __tablename__ = "program_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(40), nullable=False, unique=True, index=True)
    name = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    exercises = relationship("TemplateExercise", back_populates="template", cascade="all, delete-orphan")
    programs = relationship("WorkoutProgram", back_populates="template")


class TemplateExercise(Base):
    __tablename__ = "template_exercises"

    id = Column(Integer, primary_key=True, autoincrement=True)
    template_id = Column(Integer, ForeignKey("program_templates.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    sets = Column(Integer, nullable=False, default=3)
    repetitions = Column(Integer, nullable=False, default=10)
    weight = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    order_num = Column(Integer, nullable=False, default=1)

    template = relationship("ProgramTemplate", back_populates="exercises")


class WorkoutProgram(Base):
    __tablename__ = "workout_programs"
    __table_args__ = (UniqueConstraint("user_id", "source_key", name="uq_workout_program_user_source"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), ForeignKey("users.id"), nullable=False, index=True)
    template_id = Column(Integer, ForeignKey("program_templates.id"), nullable=True, index=True)
    source_key = Column(String(40), nullable=True)
    name = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="workout_programs")
    template = relationship("ProgramTemplate", back_populates="programs")
    exercises = relationship("ProgramExercise", back_populates="program", cascade="all, delete-orphan", order_by="ProgramExercise.order_num")


class ProgramExercise(Base):
    __tablename__ = "program_exercises"

    id = Column(Integer, primary_key=True, autoincrement=True)
    program_id = Column(Integer, ForeignKey("workout_programs.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    sets = Column(Integer, nullable=False, default=3)
    repetitions = Column(Integer, nullable=False, default=10)
    weight = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    order_num = Column(Integer, nullable=False, default=1)

    program = relationship("WorkoutProgram", back_populates="exercises")


class WorkoutSession(Base):
    """Historical workout snapshot; changing a program never changes this row."""
    __tablename__ = "workout_sessions"
    __table_args__ = (
        UniqueConstraint("user_id", "source_event_id", name="uq_workout_session_user_event"),
        CheckConstraint("session_type IN ('strength', 'cardio')", name="ck_workout_session_type"),
        CheckConstraint("estimated_duration_min IS NULL OR estimated_duration_min >= 0", name="ck_workout_session_duration"),
        CheckConstraint("estimated_calories IS NULL OR estimated_calories >= 0", name="ck_workout_session_calories"),
        Index("ix_workout_sessions_user_occurred", "user_id", "occurred_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), ForeignKey("users.id"), nullable=False, index=True)
    program_id = Column(Integer, ForeignKey("workout_programs.id", ondelete="SET NULL"), nullable=True, index=True)
    source_event_id = Column(String(128), nullable=True)
    session_type = Column(String(20), nullable=False, default="strength")
    name = Column(String(150), nullable=False)
    estimated_duration_min = Column(Float, nullable=False, default=0.0)
    estimated_calories = Column(Float, nullable=False, default=0.0)
    calories_estimated = Column(Boolean, nullable=False, default=True)
    occurred_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    notes = Column(Text, nullable=True)

    user = relationship("User", back_populates="workout_sessions")
    program = relationship("WorkoutProgram", passive_deletes=True)
    exercises = relationship("SessionExercise", back_populates="session", cascade="all, delete-orphan", order_by="SessionExercise.order_num")
    cardio = relationship("CardioDetails", back_populates="session", uselist=False, cascade="all, delete-orphan")


class SessionExercise(Base):
    """Editable exercise snapshot captured when a strength session is logged."""
    __tablename__ = "session_exercises"
    __table_args__ = (
        CheckConstraint("sets >= 0", name="ck_session_exercise_sets"),
        CheckConstraint("repetitions >= 0", name="ck_session_exercise_repetitions"),
        CheckConstraint("weight IS NULL OR weight >= 0", name="ck_session_exercise_weight"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("workout_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    sets = Column(Integer, nullable=False, default=3)
    repetitions = Column(Integer, nullable=False, default=10)
    weight = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    order_num = Column(Integer, nullable=False, default=1)

    session = relationship("WorkoutSession", back_populates="exercises")


class CardioDetails(Base):
    """Optional details for a cardio workout session."""
    __tablename__ = "cardio_details"
    __table_args__ = (
        UniqueConstraint("session_id", name="uq_cardio_details_session"),
        CheckConstraint("duration_min > 0", name="ck_cardio_duration"),
        CheckConstraint("incline_pct IS NULL OR incline_pct >= 0", name="ck_cardio_incline"),
        CheckConstraint("speed_kmh IS NULL OR speed_kmh >= 0", name="ck_cardio_speed"),
        CheckConstraint("distance_km IS NULL OR distance_km >= 0", name="ck_cardio_distance"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("workout_sessions.id", ondelete="CASCADE"), nullable=False)
    activity = Column(String(80), nullable=False)
    duration_min = Column(Float, nullable=False)
    incline_pct = Column(Float, nullable=True)
    speed_kmh = Column(Float, nullable=True)
    distance_km = Column(Float, nullable=True)
    met = Column(Float, nullable=False)

    session = relationship("WorkoutSession", back_populates="cardio")


class CardioPreset(Base):
    """A reusable, user-owned cardio configuration.

    Sessions copy these values when created, so editing a preset never changes
    historical activity records.
    """
    __tablename__ = "cardio_presets"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_cardio_preset_user_name"),
        CheckConstraint("duration_min > 0", name="ck_cardio_preset_duration"),
        CheckConstraint("incline_pct IS NULL OR incline_pct >= 0", name="ck_cardio_preset_incline"),
        CheckConstraint("speed_kmh IS NULL OR speed_kmh >= 0", name="ck_cardio_preset_speed"),
        CheckConstraint("distance_km IS NULL OR distance_km >= 0", name="ck_cardio_preset_distance"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    activity = Column(String(80), nullable=False)
    custom_name = Column(String(80), nullable=True)
    duration_min = Column(Float, nullable=False)
    incline_pct = Column(Float, nullable=True)
    speed_kmh = Column(Float, nullable=True)
    distance_km = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="cardio_presets")


class FoodCapture(Base):
    """A durable, user-owned source event for one editable food draft."""
    __tablename__ = "food_captures"
    __table_args__ = (UniqueConstraint("user_id", "source_message_id", name="uq_food_capture_user_message"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    token = Column(String(64), unique=True, nullable=False, index=True)
    user_id = Column(String(64), ForeignKey("users.id"), nullable=False, index=True)
    source = Column(String(20), nullable=False)  # image or text
    source_message_id = Column(String(128), nullable=True)
    status = Column(String(20), nullable=False, default="draft", index=True)
    ai_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="food_captures")
    drafts = relationship("FoodAnalysisDraft", back_populates="capture", cascade="all, delete-orphan", order_by="FoodAnalysisDraft.order_num")
    food_logs = relationship("FoodLog", back_populates="capture")


class FoodAnalysisDraft(Base):
    """One independent AI suggestion inside a FoodCapture."""
    __tablename__ = "food_analysis_drafts"
    __table_args__ = (
        CheckConstraint("calories >= 0", name="ck_food_draft_calories"),
        CheckConstraint("protein >= 0", name="ck_food_draft_protein"),
        CheckConstraint("carbs >= 0", name="ck_food_draft_carbs"),
        CheckConstraint("fat >= 0", name="ck_food_draft_fat"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    capture_id = Column(Integer, ForeignKey("food_captures.id"), nullable=False, index=True)
    order_num = Column(Integer, nullable=False, default=1)
    food_name = Column(String(200), nullable=False)
    portion = Column(String(150), nullable=False, default="1 ที่")
    calories = Column(Float, nullable=False, default=0.0)
    protein = Column(Float, nullable=False, default=0.0)
    carbs = Column(Float, nullable=False, default=0.0)
    fat = Column(Float, nullable=False, default=0.0)
    confidence = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    capture = relationship("FoodCapture", back_populates="drafts")


class ProcessedWebhook(Base):
    __tablename__ = "processed_webhooks"
    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(128), nullable=False, unique=True, index=True)
    user_id = Column(String(64), nullable=True, index=True)
    processed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
