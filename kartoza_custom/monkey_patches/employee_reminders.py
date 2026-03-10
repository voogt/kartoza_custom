import frappe


logger = frappe.logger("kartoza_custom.employee_reminders")


def _get_subscribed_emails(company: str | None = None) -> set[str]:
    if not frappe.db.has_column("Employee", "custom_subscribe_notification_emails"):
        return set()

    filters = {
        "status": "Active",
        "custom_subscribe_notification_emails": 1,
    }
    if company:
        filters["company"] = company

    employees = frappe.db.get_all(
        "Employee",
        filters=filters,
        fields=["user_id", "personal_email", "company_email"],
    )

    subscribed_emails = set()
    for employee in employees:
        for email in (employee.get("user_id"), employee.get("personal_email"), employee.get("company_email")):
            if email:
                subscribed_emails.add(email)

    return subscribed_emails


def _get_person_email(person: dict) -> str | None:
    return person.get("user_id") or person.get("personal_email") or person.get("company_email")


def send_birthday_reminders():
    """Custom override for HRMS birthday reminders.

    Send only to employees with custom_subscribe_notification_emails enabled.
    """
    hrms_employee_reminders = frappe.get_module("hrms.controllers.employee_reminders")

    to_send = int(frappe.db.get_single_value("HR Settings", "send_birthday_reminders") or 0)
    if not to_send:
        logger.info("Birthday reminders skipped: HR Settings send_birthday_reminders is disabled")
        return

    sender = hrms_employee_reminders.get_sender_email()
    employees_born_today = hrms_employee_reminders.get_employees_who_are_born_today()
    if not employees_born_today:
        logger.info("Birthday reminders: no employees with birthday today")
        return

    for company, birthday_persons in employees_born_today.items():
        subscribed_emails = _get_subscribed_emails(company)

        employee_emails = hrms_employee_reminders.get_all_employee_emails(company)
        birthday_person_emails = [
            hrms_employee_reminders.get_employee_email(doc) for doc in birthday_persons
        ]
        recipients = list((set(employee_emails) - set(birthday_person_emails)) & subscribed_emails)
        logger.info(
            "Birthday reminders company=%s total_employees=%s birthday_people=%s subscribed=%s recipients=%s",
            company,
            len(set(employee_emails)),
            len(birthday_persons),
            len(subscribed_emails),
            len(recipients),
        )

        if recipients:
            reminder_text, message = hrms_employee_reminders.get_birthday_reminder_text_and_message(
                birthday_persons
            )
            hrms_employee_reminders.send_birthday_reminder(
                recipients, reminder_text, birthday_persons, message, sender
            )
            logger.info("Birthday reminders sent to team recipients for company=%s", company)
        else:
            logger.info("Birthday reminders skipped for company=%s: no subscribed recipients", company)

        if len(birthday_persons) > 1:
            for person in birthday_persons:
                person_email = _get_person_email(person)
                if not person_email or person_email not in subscribed_emails:
                    logger.info(
                        "Birthday shared-reminder skipped for company=%s person=%s reason=not_subscribed_or_no_email",
                        company,
                        person.get("name"),
                    )
                    continue

                others = [d for d in birthday_persons if d != person]
                reminder_text, message = hrms_employee_reminders.get_birthday_reminder_text_and_message(others)
                hrms_employee_reminders.send_birthday_reminder(
                    person_email, reminder_text, others, message, sender
                )
                logger.info(
                    "Birthday shared-reminder sent for company=%s person=%s",
                    company,
                    person.get("name"),
                )


def send_work_anniversary_reminders():
    """Custom override for HRMS work anniversary reminders.

    Send only to employees with custom_subscribe_notification_emails enabled.
    """
    hrms_employee_reminders = frappe.get_module("hrms.controllers.employee_reminders")

    to_send = int(frappe.db.get_single_value("HR Settings", "send_work_anniversary_reminders") or 0)
    if not to_send:
        logger.info(
            "Work anniversary reminders skipped: HR Settings send_work_anniversary_reminders is disabled"
        )
        return

    sender = hrms_employee_reminders.get_sender_email()
    employees_joined_today = hrms_employee_reminders.get_employees_having_an_event_today("work_anniversary")
    if not employees_joined_today:
        logger.info("Work anniversary reminders: no employees with anniversary today")
        return

    message = frappe._("A friendly reminder of an important date for our team.")
    message += "<br>"
    message += frappe._("Everyone, let’s congratulate them on their work anniversary!")

    for company, anniversary_persons in employees_joined_today.items():
        subscribed_emails = _get_subscribed_emails(company)

        employee_emails = hrms_employee_reminders.get_all_employee_emails(company)
        anniversary_person_emails = [
            hrms_employee_reminders.get_employee_email(doc) for doc in anniversary_persons
        ]
        recipients = list((set(employee_emails) - set(anniversary_person_emails)) & subscribed_emails)
        logger.info(
            "Work anniversary reminders company=%s total_employees=%s anniversary_people=%s subscribed=%s recipients=%s",
            company,
            len(set(employee_emails)),
            len(anniversary_persons),
            len(subscribed_emails),
            len(recipients),
        )

        if recipients:
            reminder_text = hrms_employee_reminders.get_work_anniversary_reminder_text(anniversary_persons)
            hrms_employee_reminders.send_work_anniversary_reminder(
                recipients, reminder_text, anniversary_persons, message, sender
            )
            logger.info("Work anniversary reminders sent to team recipients for company=%s", company)
        else:
            logger.info(
                "Work anniversary reminders skipped for company=%s: no subscribed recipients", company
            )

        if len(anniversary_persons) > 1:
            for person in anniversary_persons:
                person_email = _get_person_email(person)
                if not person_email or person_email not in subscribed_emails:
                    logger.info(
                        "Work anniversary shared-reminder skipped for company=%s person=%s reason=not_subscribed_or_no_email",
                        company,
                        person.get("name"),
                    )
                    continue

                others = [d for d in anniversary_persons if d != person]
                reminder_text = hrms_employee_reminders.get_work_anniversary_reminder_text(others)
                hrms_employee_reminders.send_work_anniversary_reminder(
                    person_email, reminder_text, others, message, sender
                )
                logger.info(
                    "Work anniversary shared-reminder sent for company=%s person=%s",
                    company,
                    person.get("name"),
                )


def apply_monkey_patches(*args, **kwargs):
    """Monkey patch HRMS reminder methods from kartoza_custom.

    Safe to run repeatedly (request/job lifecycle).
    """
    hrms_employee_reminders = frappe.get_module("hrms.controllers.employee_reminders")

    if getattr(hrms_employee_reminders, "_kartoza_birthday_patch_applied", False):
        logger.debug("Employee reminders monkey patches already applied")
        return

    hrms_employee_reminders._kartoza_original_send_birthday_reminders = (
        hrms_employee_reminders.send_birthday_reminders
    )
    hrms_employee_reminders.send_birthday_reminders = send_birthday_reminders

    hrms_employee_reminders._kartoza_original_send_work_anniversary_reminders = (
        hrms_employee_reminders.send_work_anniversary_reminders
    )
    hrms_employee_reminders.send_work_anniversary_reminders = send_work_anniversary_reminders

    hrms_employee_reminders._kartoza_birthday_patch_applied = True
    logger.info("Applied monkey patches for birthday and work anniversary reminders")
