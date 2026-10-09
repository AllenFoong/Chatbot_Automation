"""reminders 表、wa_contacts 的 opt-out 栏位：数据库挡掉不合理的资料。假号码。"""

from datetime import date, datetime, timezone

from app.db.models import OptOutBy, Reminder, ReminderStatus, WaContact
from app.db.reminders import opted_out_phones, record_opened, set_opt_out
from tests.database import add_staff, assert_rejected

DAY = date(2026, 10, 9)
NOW = datetime(2026, 10, 8, 2, 0, tzinfo=timezone.utc)


def reminder(**kw):
    values = dict(appointment_date=DAY, wa_phone="60120000001", status=ReminderStatus.OPENED, body="Demo",
                  gpis_appointment_ids=[1])
    return Reminder(**{**values, **kw})


def test_one_row_per_number_and_day(session):
    session.add(reminder())
    session.flush()
    assert_rejected(session, reminder())
    session.add(reminder(appointment_date=date(2026, 10, 10)))
    session.flush()


def test_bad_values_are_rejected(session):
    assert_rejected(session, reminder(wa_phone="012-000 0001"))
    assert_rejected(session, WaContact(wa_phone="60120000002", reminders_opt_out_by=OptOutBy.STAFF))
    staff = add_staff(session)
    assert_rejected(session, WaContact(wa_phone="60120000003", reminders_opt_out_at=NOW,
                                       reminders_opt_out_by=OptOutBy.PATIENT, reminders_opt_out_staff_id=staff.id))


def test_record_opened_twice_keeps_one_row(session):
    amy, ben = add_staff(session, "amy"), add_staff(session, "ben")
    record_opened(session, DAY, "60120000001", "first", [2, 1], amy)
    r = record_opened(session, DAY, "60120000001", "second", [1, 2, 3], ben)
    assert session.query(Reminder).count() == 1
    assert (r.body, r.gpis_appointment_ids, r.staff_id) == ("second", [1, 2, 3], ben.id)


def test_opt_out_and_back(session):
    amy = add_staff(session)
    set_opt_out(session, "012-000 0001", True, amy)
    assert opted_out_phones(session) == {"60120000001"}
    set_opt_out(session, "60120000001", False, amy)
    assert opted_out_phones(session) == frozenset()
