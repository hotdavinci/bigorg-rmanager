import enum
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, ForeignKey, Text, Boolean, Enum, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

class CampaignStatus(str, enum.Enum):
    DRAFT="DRAFT"; PROCESSING="PROCESSING"; PROCESSING_FAILED="PROCESSING_FAILED"; READY_TO_SCHEDULE="READY_TO_SCHEDULE"; SCHEDULE_GENERATED="SCHEDULE_GENERATED"; ACTIVE="ACTIVE"; PAUSED="PAUSED"; COMPLETED="COMPLETED"; CANCELLED="CANCELLED"; ERROR="ERROR"
class PostStatus(str, enum.Enum):
    PENDING="PENDING"; CLAIMED="CLAIMED"; UPLOADING="UPLOADING"; WAITING_META="WAITING_META"; PUBLISHING="PUBLISHING"; PUBLISHED="PUBLISHED"; FAILED="FAILED"; SKIPPED="SKIPPED"; PAUSED="PAUSED"; CANCELLED="CANCELLED"
class Media(Base):
    __tablename__="media_files"
    id: Mapped[int]=mapped_column(primary_key=True); original_name: Mapped[str]=mapped_column(String(255)); stored_name: Mapped[str]=mapped_column(String(255)); relative_path: Mapped[str]=mapped_column(String(500), unique=True)
    kind: Mapped[str]=mapped_column(String(20)); extension: Mapped[str]=mapped_column(String(10)); size: Mapped[int]=mapped_column(Integer); sha256: Mapped[str]=mapped_column(String(64)); status: Mapped[str]=mapped_column(String(30), default="Disponível")
    original_media_id: Mapped[int|None]=mapped_column(ForeignKey("media_files.id")); created_at: Mapped[datetime]=mapped_column(DateTime, default=datetime.utcnow)
class InstagramAccount(Base):
    __tablename__="instagram_accounts"
    id: Mapped[int]=mapped_column(primary_key=True); meta_account_id: Mapped[str]=mapped_column(String(100), unique=True); username: Mapped[str]=mapped_column(String(120), default=""); display_name: Mapped[str]=mapped_column(String(160), default="")
    profile_picture_url: Mapped[str]=mapped_column(String(500), default=""); encrypted_token: Mapped[str]=mapped_column(Text); token_type: Mapped[str]=mapped_column(String(30), default="instagram_user")
    token_expires_at: Mapped[datetime|None]=mapped_column(DateTime); active: Mapped[bool]=mapped_column(Boolean, default=True); connected_at: Mapped[datetime]=mapped_column(DateTime, default=datetime.utcnow); last_verified_at: Mapped[datetime|None]=mapped_column(DateTime); last_error: Mapped[str]=mapped_column(Text, default="")
class OAuthState(Base):
    __tablename__="oauth_states"
    state: Mapped[str]=mapped_column(String(128), primary_key=True); created_at: Mapped[datetime]=mapped_column(DateTime, default=datetime.utcnow)
class Script(Base):
    __tablename__="processing_scripts"
    id: Mapped[int]=mapped_column(primary_key=True); name: Mapped[str]=mapped_column(String(120)); description: Mapped[str]=mapped_column(Text, default=""); relative_path: Mapped[str]=mapped_column(String(500), unique=True); active: Mapped[bool]=mapped_column(Boolean, default=True); created_at: Mapped[datetime]=mapped_column(DateTime, default=datetime.utcnow)
class Campaign(Base):
    __tablename__="campaigns"
    id: Mapped[int]=mapped_column(primary_key=True); name: Mapped[str]=mapped_column(String(150)); description: Mapped[str]=mapped_column(Text, default=""); timezone: Mapped[str]=mapped_column(String(64), default="America/Sao_Paulo"); status: Mapped[CampaignStatus]=mapped_column(Enum(CampaignStatus), default=CampaignStatus.DRAFT); script_id: Mapped[int|None]=mapped_column(ForeignKey("processing_scripts.id")); cover_path: Mapped[str]=mapped_column(String(500), default=""); caption_list_id: Mapped[int|None]=mapped_column(ForeignKey("caption_lists.id")); caption_text: Mapped[str]=mapped_column(Text, default=""); created_at: Mapped[datetime]=mapped_column(DateTime, default=datetime.utcnow)
class CaptionList(Base):
    __tablename__="caption_lists"
    id: Mapped[int]=mapped_column(primary_key=True); name: Mapped[str]=mapped_column(String(255)); items_json: Mapped[str]=mapped_column(Text, default="[]"); relative_path: Mapped[str]=mapped_column(String(500), default=""); created_at: Mapped[datetime]=mapped_column(DateTime, default=datetime.utcnow)
class CampaignAccount(Base):
    __tablename__="campaign_accounts"; __table_args__=(UniqueConstraint("campaign_id","account_id",name="uq_campaign_account"),)
    id: Mapped[int]=mapped_column(primary_key=True); campaign_id: Mapped[int]=mapped_column(ForeignKey("campaigns.id")); account_id: Mapped[int]=mapped_column(ForeignKey("instagram_accounts.id"))
class CampaignSourceMedia(Base):
    __tablename__="campaign_source_media"; __table_args__=(UniqueConstraint("campaign_id","media_id",name="uq_campaign_source_media"),)
    id: Mapped[int]=mapped_column(primary_key=True); campaign_id: Mapped[int]=mapped_column(ForeignKey("campaigns.id")); media_id: Mapped[int]=mapped_column(ForeignKey("media_files.id"))
class CampaignScript(Base):
    __tablename__="campaign_scripts"; __table_args__=(UniqueConstraint("campaign_id","position",name="uq_campaign_script_position"),)
    id: Mapped[int]=mapped_column(primary_key=True); campaign_id: Mapped[int]=mapped_column(ForeignKey("campaigns.id")); script_id: Mapped[int]=mapped_column(ForeignKey("processing_scripts.id")); position: Mapped[int]=mapped_column(Integer)
class CampaignScheduleRule(Base):
    __tablename__="campaign_schedule_rules"
    id: Mapped[int]=mapped_column(primary_key=True); campaign_id: Mapped[int]=mapped_column(ForeignKey("campaigns.id"),unique=True); start_date: Mapped[str]=mapped_column(String(10)); days: Mapped[int]=mapped_column(Integer); intervals: Mapped[str]=mapped_column(Text); strategy: Mapped[str]=mapped_column(String(20),default="sequential")
class ProcessedCover(Base):
    __tablename__="processed_covers"
    id: Mapped[int]=mapped_column(primary_key=True); campaign_id: Mapped[int]=mapped_column(ForeignKey("campaigns.id")); original_media_id: Mapped[int]=mapped_column(ForeignKey("media_files.id")); post_id: Mapped[int|None]=mapped_column(ForeignKey("scheduled_posts.id"), unique=True); relative_path: Mapped[str]=mapped_column(String(500)); sha256: Mapped[str]=mapped_column(String(64)); created_at: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class ScheduledPostCover(Base):
    __tablename__="scheduled_post_covers"
    id: Mapped[int]=mapped_column(primary_key=True); post_id: Mapped[int]=mapped_column(ForeignKey("scheduled_posts.id"),unique=True); cover_id: Mapped[int]=mapped_column(ForeignKey("processed_covers.id"))
class PublicationAttempt(Base):
    __tablename__="publication_attempts"
    id: Mapped[int]=mapped_column(primary_key=True); post_id: Mapped[int]=mapped_column(ForeignKey("scheduled_posts.id")); status: Mapped[str]=mapped_column(String(30)); message: Mapped[str]=mapped_column(Text,default=""); meta_media_id: Mapped[str]=mapped_column(String(100),default=""); created_at: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow); finished_at: Mapped[datetime|None]=mapped_column(DateTime)
class ProcessingExecution(Base):
    __tablename__="processing_executions"
    id: Mapped[int]=mapped_column(primary_key=True); campaign_id: Mapped[int]=mapped_column(ForeignKey("campaigns.id")); script_id: Mapped[int]=mapped_column(ForeignKey("processing_scripts.id")); status: Mapped[str]=mapped_column(String(30), default="RUNNING"); workspace: Mapped[str]=mapped_column(String(500)); stdout: Mapped[str]=mapped_column(Text, default=""); stderr: Mapped[str]=mapped_column(Text, default=""); exit_code: Mapped[int|None]=mapped_column(Integer); started_at: Mapped[datetime]=mapped_column(DateTime, default=datetime.utcnow); finished_at: Mapped[datetime|None]=mapped_column(DateTime)
class ScheduledPost(Base):
    __tablename__="scheduled_posts"; __table_args__=(UniqueConstraint("campaign_id", "account_id", "scheduled_for", "position", name="uq_schedule_occurrence"),)
    id: Mapped[int]=mapped_column(primary_key=True); campaign_id: Mapped[int]=mapped_column(ForeignKey("campaigns.id")); account_id: Mapped[int]=mapped_column(Integer); processed_media_id: Mapped[int]=mapped_column(ForeignKey("media_files.id"), nullable=False); caption: Mapped[str]=mapped_column(Text, default=""); scheduled_for: Mapped[datetime]=mapped_column(DateTime); position: Mapped[int]=mapped_column(Integer, default=0); status: Mapped[PostStatus]=mapped_column(Enum(PostStatus), default=PostStatus.PENDING); attempts: Mapped[int]=mapped_column(Integer, default=0); claimed_at: Mapped[datetime|None]=mapped_column(DateTime)
