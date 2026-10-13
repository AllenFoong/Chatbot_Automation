"""本系统的数据库表（PostgreSQL）。表结构以这个文件为准；改了这里，要再加一个 Alembic migration。

1. 诊所设置（原本写在 clinic_rules.py；Phase 4 员工可以在 Admin Platform 修改）
   doctors、doctor_schedules、services、clinic_closures、doctor_leaves、clinic_settings
2. WhatsApp 对话和预约请求
   wa_contacts（一个 WhatsApp 号码）→ conversations（一段对话）→ messages（每条消息）
   customers（一位病人）← appointment_requests（预约请求，员工确认后手动录入 GPiS，D6）
   staff（员工账号）
3. 预约提醒（Phase 5b）
   reminders（一个号码、一个预约日期的提醒）；wa_contacts 上记这个号码要不要提醒（opt-out）
   reminder_stats（提醒删掉之后留下的每天数目，A10）

第 2、3 部分会存病人资料（名字、电话、消息内容）：开发和测试只用假数据（CLAUDE.md 规则 4）。
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime, time

from sqlalchemy import (
    CheckConstraint, Enum, ForeignKey, Index, Integer, SmallInteger, String, Text, UniqueConstraint, false, func, text,
    true,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ConversationMode(enum.StrEnum):
    BOT = "BOT"            # AI 回复
    HUMAN = "HUMAN"        # 员工接手，AI 不再回复
    CLOSED = "CLOSED"      # 已结束；病人再发消息会开一段新的对话


class Sender(enum.StrEnum):
    CUSTOMER = "CUSTOMER"  # 病人发来的（IN）
    BOT = "BOT"            # AI 发出的（OUT）
    STAFF = "STAFF"        # 员工发出的（OUT）


class WaStatus(enum.StrEnum):
    """发出的消息送到哪一步（WhatsApp 的 status webhook 会更新，Phase 5）。"""
    ACCEPTED = "ACCEPTED"      # WhatsApp 收下了（API 回了消息 ID），还没送出
    SENT = "SENT"              # 已送出（一个勾）
    DELIVERED = "DELIVERED"    # 病人手机收到了（两个勾）
    READ = "READ"              # 病人看过了（蓝色两个勾）
    FAILED = "FAILED"          # 送不到，原因在 wa_error


class RequestStatus(enum.StrEnum):
    PENDING = "PENDING"        # 等员工确认
    CONFIRMED = "CONFIRMED"    # 员工确认，录入 GPiS
    REJECTED = "REJECTED"      # 员工拒绝
    CANCELLED = "CANCELLED"    # 病人取消


class ReminderStatus(enum.StrEnum):
    """一条提醒走到哪一步。现在只有员工按 Open in WhatsApp（D54）；系统自己发要等 5c，到时再加 SENDING、ACCEPTED 等。"""
    OPENED = "OPENED"          # 员工按了 Open in WhatsApp（系统不知道最后有没有按 Enter）
    NOT_SENT = "NOT_SENT"      # 员工说没有发出去（按错、病人刚打电话来等）


class OptOutBy(enum.StrEnum):
    PATIENT = "PATIENT"        # 病人自己说不要（5c 之后：回 STOP）
    STAFF = "STAFF"            # 员工标记（例：签名表的 Remark 写 NO WA，D55）


class StaffRole(enum.StrEnum):
    ADMIN = "ADMIN"        # 还可以改设置（排班、疗程、假期）
    STAFF = "STAFF"


def _enum(cls: type[enum.StrEnum], name: str) -> Enum:
    """存成 VARCHAR(20) + CHECK，不用 PostgreSQL 的 ENUM 类型：以后加新的值比较简单。"""
    return Enum(cls, name=name, native_enum=False, create_constraint=True, length=20)


def _on_grid(column: str) -> CheckConstraint:
    """时间必须在 30 分钟的格上（:00 或 :30），否则对不上 GPiS 的 TimeSlot。"""
    return CheckConstraint(
        f"{column} IS NULL OR (EXTRACT(MINUTE FROM {column}) IN (0, 30) AND EXTRACT(SECOND FROM {column}) = 0)",
        name=f"{column}_on_grid",
    )


# ====================================================================
# 1. 诊所设置
# ====================================================================

class Doctor(Base):
    """医生。离职的医生改成 active = false，不要删除（旧的预约请求还会用到）。"""

    __tablename__ = "doctors"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)        # = GPiS 的 DoctorID，例 PHANG
    display_name: Mapped[str] = mapped_column(String(100))
    remark_tag: Mapped[str | None] = mapped_column(String(5))            # Remarks 里的 (P) / (G)
    active: Mapped[bool] = mapped_column(server_default=true())

    schedules: Mapped[list[DoctorSchedule]] = relationship(back_populates="doctor", cascade="all, delete-orphan")

    __table_args__ = (
        # availability.py 会把输入转成大写再比对
        CheckConstraint("id = upper(btrim(id))", name="id_upper"),
    )


class DoctorSchedule(Base):
    """某医生星期几的排班（= clinic_rules.DaySchedule）。break_start … break_end 之间的格不能约。"""

    __tablename__ = "doctor_schedules"

    doctor_id: Mapped[str] = mapped_column(ForeignKey("doctors.id", ondelete="CASCADE"), primary_key=True)
    weekday: Mapped[int] = mapped_column(SmallInteger, primary_key=True)   # 1 = 星期一 … 7 = 星期日
    is_working: Mapped[bool]
    start_time: Mapped[time | None]
    last_slot: Mapped[time | None]          # 最后一个可预约的时段（W21）
    break_start: Mapped[time | None]        # 午休整个小时都不能约（W20）
    break_end: Mapped[time | None]

    doctor: Mapped[Doctor] = relationship(back_populates="schedules")

    __table_args__ = (
        CheckConstraint("weekday BETWEEN 1 AND 7", name="weekday"),
        CheckConstraint(
            "NOT is_working OR (start_time IS NOT NULL AND last_slot IS NOT NULL AND start_time <= last_slot)",
            name="working_hours",
        ),
        CheckConstraint(
            "(break_start IS NULL) = (break_end IS NULL) AND (break_start IS NULL OR break_start < break_end)",
            name="break",
        ),
        *(_on_grid(c) for c in ("start_time", "last_slot", "break_start", "break_end")),
    )


class Service(Base):
    """疗程代码，和 GPiS Remarks 用同一套（clinic-workflow.md 第 6 节），员工录入 GPiS 时可以照抄。"""

    __tablename__ = "services"

    code: Mapped[str] = mapped_column(String(20), primary_key=True)        # 例 S+P、C/UP、OR
    name: Mapped[str] = mapped_column(String(100))
    can_be_third: Mapped[bool] = mapped_column(server_default=false())     # 能当一格的第 3 人（W15）
    may_need_1h: Mapped[bool] = mapped_column(server_default=false())      # 可能要 1 hour，由员工看情况决定（W16、W17）
    ai_can_book: Mapped[bool] = mapped_column(server_default=false())      # AI 能自己推荐时段；否 = 收集需求后转员工（D15、D16）
    # 属于哪一种多步骤疗程：IMPLANT / DENTURE / ORTHO / RCT / CROWN / BRIDGE（不是多步骤 = NULL）。
    # 后续预约要找"上一次同类疗程"的医生（W9、D16），所以要知道哪些代码是同一类
    treatment_group: Mapped[str | None] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(server_default=true())

    __table_args__ = (CheckConstraint("code = upper(btrim(code))", name="code_upper"),)

    @property
    def multi_step(self) -> bool:
        return self.treatment_group is not None


class ClinicClosure(Base):
    """诊所休息日：全国 + Johor 公共假期、农历新年多休的日子（W1、W14）。Phase 4 的假期管理模块维护。"""

    __tablename__ = "clinic_closures"

    closure_date: Mapped[date] = mapped_column(primary_key=True)
    reason: Mapped[str] = mapped_column(String(100))


class DoctorLeave(Base):
    """本系统记录的医生请假（备用；GPiS 里的 OFF DAY 也会检查，W25）。"""

    __tablename__ = "doctor_leaves"

    doctor_id: Mapped[str] = mapped_column(ForeignKey("doctors.id", ondelete="CASCADE"), primary_key=True)
    leave_date: Mapped[date] = mapped_column(primary_key=True)
    reason: Mapped[str | None] = mapped_column(String(100))


class ClinicSettings(Base):
    """其他设置。只有一行（id = 1）：每个设置一栏，有类型、有范围检查。"""

    __tablename__ = "clinic_settings"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False, server_default=text("1"))
    max_per_slot: Mapped[int] = mapped_column(SmallInteger, server_default=text("3"))           # 每格最多几人（W22）
    max_per_slot_for_ai: Mapped[int] = mapped_column(SmallInteger, server_default=text("3"))    # 改成 2 = AI 不用第 3 个名额
    clinic_contact_id: Mapped[int]          # GPiS 里诊所自己当联系人的 ContactID（统计 B6）

    __table_args__ = (
        CheckConstraint("id = 1", name="single_row"),
        CheckConstraint("max_per_slot BETWEEN 1 AND 3", name="max_per_slot"),
        CheckConstraint("max_per_slot_for_ai BETWEEN 1 AND 3", name="max_per_slot_for_ai"),
    )


# ====================================================================
# 2. WhatsApp 对话和预约请求
# ====================================================================

class Staff(Base):
    """员工账号。登录功能 Phase 4 才做；password_hash 绝不存明文密码。"""

    __tablename__ = "staff"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    role: Mapped[StaffRole] = mapped_column(_enum(StaffRole, "staff_role"), server_default=StaffRole.STAFF.value)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(server_default=true())
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        # 登录时会把输入转成小写再比对
        CheckConstraint("username = lower(btrim(username)) AND username <> ''", name="username_lower"),
    )


class StaffSession(Base):
    """员工登录后的 session（Phase 4）。

    Cookie 里放随机 token；数据库只存它的 SHA-256，数据库外泄也不能拿来登录。
    """

    __tablename__ = "staff_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[datetime]

    staff: Mapped[Staff] = relationship()


class WaContact(Base):
    """一个 WhatsApp 号码。一个号码可能代表几位病人（家人共用，统计 B11），所以对话按号码分，不按病人分。"""

    __tablename__ = "wa_contacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    wa_phone: Mapped[str] = mapped_column(String(20), unique=True)     # 国际格式、只有数字，例 60123456789
    profile_name: Mapped[str | None] = mapped_column(String(100))      # 病人在 WhatsApp 上自己设的名字
    # 这个号码不要预约提醒（整个号码，家人也一起，D46）；NULL = 照常提醒
    reminders_opt_out_at: Mapped[datetime | None]
    reminders_opt_out_by: Mapped[OptOutBy | None] = mapped_column(_enum(OptOutBy, "opt_out_by"))
    reminders_opt_out_staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"))   # 哪位员工标记的
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    conversations: Mapped[list[Conversation]] = relationship(back_populates="wa_contact")

    __table_args__ = (
        CheckConstraint("wa_phone ~ '^[0-9]{8,15}$'", name="wa_phone_digits"),
        CheckConstraint("(reminders_opt_out_at IS NULL) = (reminders_opt_out_by IS NULL)", name="opt_out_together"),
        CheckConstraint("reminders_opt_out_staff_id IS NULL OR reminders_opt_out_by = 'STAFF'",
                        name="opt_out_staff_only_for_staff"),
    )


class Customer(Base):
    """一位病人。新病人还没有 GPiS ContactID（员工录入 GPiS 之后才有）。"""

    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(20), index=True)   # 国际格式；不唯一（家人共用号码）
    gpis_contact_id: Mapped[int | None] = mapped_column(unique=True)    # = GPiS Tbl_CAH_Contact.ContactID
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (CheckConstraint("phone ~ '^[0-9]{8,15}$'", name="phone_digits"),)


class Conversation(Base):
    """和一个 WhatsApp 号码的一段对话。"""

    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    wa_contact_id: Mapped[int] = mapped_column(ForeignKey("wa_contacts.id"), index=True)
    mode: Mapped[ConversationMode] = mapped_column(
        _enum(ConversationMode, "conversation_mode"), server_default=ConversationMode.BOT.value
    )
    assigned_staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"))
    handover_reason: Mapped[str | None] = mapped_column(Text)          # AI 为什么转人工（给员工看）
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    closed_at: Mapped[datetime | None]

    wa_contact: Mapped[WaContact] = relationship(back_populates="conversations")
    assigned_staff: Mapped[Staff | None] = relationship()
    messages: Mapped[list[Message]] = relationship(back_populates="conversation", order_by="Message.id")

    __table_args__ = (
        # 由数据库保证：一个号码同时最多一段没结束的对话（两条消息同时到，也不会开出两段）
        Index(
            "uq_conversations_open_per_contact", "wa_contact_id",
            unique=True, postgresql_where=text("mode <> 'CLOSED'"),
        ),
        CheckConstraint("(mode = 'CLOSED') = (closed_at IS NOT NULL)", name="closed_at"),
    )


class Message(Base):
    """一条进出的消息。方向由 sender 决定：CUSTOMER = 收到，BOT / STAFF = 发出。"""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    sender: Mapped[Sender] = mapped_column(_enum(Sender, "message_sender"))
    staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"))    # 哪位员工发的；在手机 App 上发的不知道是谁
    body: Mapped[str] = mapped_column(Text)
    # WhatsApp 的消息 ID：同一条消息 WhatsApp 可能送来两次，用它去重
    wa_message_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    # 发出的消息送到哪一步（Phase 5）。病人发来的、Phase 5 之前的（假资料）没有
    wa_status: Mapped[WaStatus | None] = mapped_column(_enum(WaStatus, "message_wa_status"))
    wa_error: Mapped[str | None] = mapped_column(Text)        # 送不到的原因（WhatsApp 的错误信息，给员工看）
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    conversation: Mapped[Conversation] = relationship(back_populates="messages")

    __table_args__ = (
        CheckConstraint("staff_id IS NULL OR sender = 'STAFF'", name="staff_id_only_for_staff"),
        CheckConstraint("wa_status IS NULL OR sender <> 'CUSTOMER'", name="wa_status_only_outgoing"),
        CheckConstraint("wa_error IS NULL OR wa_status = 'FAILED'", name="wa_error_only_failed"),
    )


class AppointmentRequest(Base):
    """预约请求：AI（或员工）建立，员工确认后手动录入 GPiS（D6）。"""

    __tablename__ = "appointment_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)       # 帮哪一位病人约
    # 从哪段对话来；员工自己建的（例如电话预约）没有
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey("conversations.id"), index=True)
    service_code: Mapped[str] = mapped_column(ForeignKey("services.code"))
    doctor_id: Mapped[str | None] = mapped_column(ForeignKey("doctors.id"))
    preferred_date: Mapped[date | None]
    preferred_slot: Mapped[time | None]
    duration_minutes: Mapped[int] = mapped_column(SmallInteger, server_default=text("30"))   # 30 / 60（员工决定）
    status: Mapped[RequestStatus] = mapped_column(
        _enum(RequestStatus, "request_status"), server_default=RequestStatus.PENDING.value
    )
    notes: Mapped[str | None] = mapped_column(Text)               # 病人说的需求、员工备注
    group_id: Mapped[uuid.UUID | None]                            # 一起来的几位病人共用（Remarks 的 WITH，W8）
    # 员工录入 GPiS 后的 AppointmentID（改期时不变，W5）。GPiS 画面不显示这个 ID，将来由系统对上
    gpis_appointment_id: Mapped[int | None]
    handled_by: Mapped[int | None] = mapped_column(ForeignKey("staff.id"))
    handled_at: Mapped[datetime | None]                           # 最后一次改状态的时间
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    customer: Mapped[Customer] = relationship()
    service: Mapped[Service] = relationship()
    conversation: Mapped[Conversation | None] = relationship()

    __table_args__ = (
        CheckConstraint("preferred_slot IS NULL OR preferred_date IS NOT NULL", name="slot_needs_date"),
        _on_grid("preferred_slot"),
        CheckConstraint("duration_minutes > 0 AND mod(duration_minutes, 30) = 0", name="duration"),
        CheckConstraint("(status = 'PENDING') = (handled_at IS NULL)", name="handled_at"),
    )


# ====================================================================
# 3. 预约提醒（Phase 5b，docs/architecture.md 第 8 节）
# ====================================================================

class Reminder(Base):
    """一个号码、一个预约日期的提醒（家人合成一条，D49）。

    名单本身每次都从 GPiS 重新算，不存；这里只记员工做过什么（按过 Open in WhatsApp、没有发出去），
    换页、重新整理、两位员工同时看，都看得到，避免同一个号码发两次。
    """

    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(primary_key=True)
    appointment_date: Mapped[date]
    wa_phone: Mapped[str] = mapped_column(String(20))                  # 国际格式、只有数字
    status: Mapped[ReminderStatus] = mapped_column(_enum(ReminderStatus, "reminder_status"))
    body: Mapped[str] = mapped_column(Text)                            # 打开时填好的消息（有病人名字）
    # 这条提醒包括哪几个 GPiS 预约：之后 GPiS 多了、少了预约，页面会提醒员工再看一次
    gpis_appointment_ids: Mapped[list[int]] = mapped_column(ARRAY(Integer))
    staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"))   # 最后改状态的员工
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    staff: Mapped[Staff | None] = relationship()

    __table_args__ = (
        # 同一个号码、同一个预约日期只有一条（D45）：再按一次是更新这一条
        UniqueConstraint("appointment_date", "wa_phone"),
        CheckConstraint("wa_phone ~ '^[0-9]{8,15}$'", name="wa_phone_digits"),
    )


class ReminderStats(Base):
    """提醒删掉之后留下的数目（A10、D67）：一个预约日期一行，没有号码、名字、员工。

    预约日期过了 90 天，reminders 那几行整行删掉，删之前把数目加到这里（app/db/retention.py）。
    """

    __tablename__ = "reminder_stats"

    appointment_date: Mapped[date] = mapped_column(primary_key=True)
    opened: Mapped[int] = mapped_column(server_default=text("0"))                # 几个号码按过 Open in WhatsApp
    not_sent: Mapped[int] = mapped_column(server_default=text("0"))              # 几个号码改回 Not sent
    opened_appointments: Mapped[int] = mapped_column(server_default=text("0"))   # 按过的那些号码一共几个 GPiS 预约

    __table_args__ = (
        CheckConstraint("opened >= 0 AND not_sent >= 0 AND opened_appointments >= 0", name="counts"),
    )
