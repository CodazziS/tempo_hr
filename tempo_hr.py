from openerp.osv import fields, osv
import time
import datetime
from pprint import pprint
import pytz
import openerp
from openerp import tools, api
from openerp.osv import osv, fields
import dateutil


@api.model
def _tz_get(self):
    return [(tz,tz) for tz in sorted(pytz.all_timezones, key=lambda tz: tz if not tz.startswith('Etc/') else '_')]

@api.multi
def _get_tz_offset(self, name, args):
    return dict(
        (p.id, datetime.datetime.now(pytz.timezone(p.tz or 'GMT')).strftime('%z'))
        for p in self)


class tempo_hr_time(osv.osv):
    _name = "hr.employee"
    _inherit = 'hr.employee'

    _columns = {
        'tz': fields.selection(
            _tz_get,
            'Timezone',
            size=64,
            help="The partner's timezone, used to output proper date and time values inside printed reports. "
            "It is important to set a value for this field. You should use the same timezone "
            "that is otherwise used to pick and render date and time values: your computer's timezone."),
        'tz_offset': fields.function(_get_tz_offset,
                                     type='char',
                                     size=5,
                                     string='Timezone offset',
                                     invisible=True),
    }

    _defaults = {
        'tz': api.model(lambda self: self.env.context.get('tz', False)),
    }


class tempo_hr_calc(osv.osv):
    _name = "hr.attendance"
    _inherit = 'hr.attendance'

    def cron_tempo_hr(self, cr, uid, context=None):
        today = datetime.datetime.now()
        employees = self.pool.get('hr.employee')\
            .search(cr, uid,
                    [('active', '=', False)])
        for employee in self.pool.get('hr.employee').browse(cr, uid, employees):
            last_sign = employee.last_sign
            last_sign_date = ""

            if type(last_sign) is str:
                last_sign = datetime.datetime.strptime(last_sign, '%Y-%m-%d %H:%M:%S')
                last_sign_date = str(last_sign.date())

            if last_sign_date != str(today.date()):
                working_days = employee.contract_id\
                    .working_hours.attendance_ids
                for day in working_days:
                    if int(day.dayofweek) == today.weekday():
                        if employee.tz is not False:
                            tz = pytz.timezone(employee.tz)
                        else:
                            tz = pytz.utc

                        holidays = self.pool.get('public.holidays.holidays')\
                            .is_holiday(cr, uid, today.date())
                        if holidays is False:
                            # ***** SIGN IN *****
                            time_day = str(day.hour_from).split('.')
                            name_date = str(today.date()) + " "
                            name_date += str(time_day[0]) + ":"
                            if len(str(time_day[1])) == 1:
                                name_date += "0" + str(time_day[1])
                            else:
                                name_date += str(time_day[1])
                            name_date += ":00"

                            name = datetime.datetime\
                                .strptime(name_date, '%Y-%m-%d %H:%M:%S')
                            start_date = tz.localize(name, is_dst=None)
                            now_utc = start_date.astimezone(pytz.utc)

                            vals = {
                                'action': 'sign_in',
                                'name': now_utc,
                                'employee_id': employee.id,
                            }
                            hr_attendance = self.pool.get('hr.attendance')
                            hr_attendance.create(cr, uid, vals, context=context)

                            # ***** SIGN OUT *****
                            time_day = str(day.hour_to).split('.')
                            name_date = str(today.date()) + " "
                            name_date += str(time_day[0]) + ":"
                            if len(str(time_day[1])) == 1:
                                name_date += "0" + str(time_day[1])
                            else:
                                name_date += str(time_day[1])
                            name_date += ":00"

                            name = datetime.datetime\
                                .strptime(name_date, '%Y-%m-%d %H:%M:%S')
                            start_date = tz.localize(name, is_dst=None)
                            now_utc = start_date.astimezone(pytz.utc)

                            vals = {
                                'action': 'sign_out',
                                'name': now_utc,
                                'employee_id': employee.id,
                            }
                            hr_attendance = self.pool.get('hr.attendance')
                            hr_attendance.create(cr, uid, vals, context=context)
        return None

    def _worked_hours_compute(self, cr, uid, ids, fieldnames, args, context=None):
        res = {}
        for obj in self.browse(cr, uid, ids, context=context):
            if obj.action == 'sign_in':
                res[obj.id] = 0
            elif obj.action == 'sign_out':
                # Get the associated sign-in
                last_signin_id = self.search(cr, uid, [
                    ('employee_id', '=', obj.employee_id.id),
                    ('name', '<', obj.name), ('action', '=', 'sign_in')
                ], limit=1, order='name DESC')
                if last_signin_id:
                    last_signin = self.browse(cr, uid, last_signin_id, context=context)[0]
                    last_signin_datetime = datetime.datetime.strptime(last_signin.name, '%Y-%m-%d %H:%M:%S')
                    signout_datetime = datetime.datetime.strptime(obj.name, '%Y-%m-%d %H:%M:%S')
                    workedhours_datetime = (signout_datetime - last_signin_datetime)
                    seconds = workedhours_datetime.seconds % 60
                    minutes = (workedhours_datetime.seconds / 60) % 60
                    hours = (workedhours_datetime.seconds / 60) / 60
                    minutes_dec = float(minutes) / 60
                    seconds_dec = float(seconds) / 3600
                    res[obj.id] = float(hours) + float(minutes_dec) + float(seconds_dec)
                else:
                    res[obj.id] = False
        return res

    def _calendar_start(self, cr, uid, ids, fieldnames, args, context=None):
        res = {}
        for obj in self.browse(cr, uid, ids, context=context):
            if obj.action == 'sign_in':
                res[obj.id] = None
            elif obj.action == 'sign_out':
                date_stop = datetime.datetime.strptime(obj.name, '%Y-%m-%d %H:%M:%S')
                date_delay = obj.worked_hours
                hours = int(date_delay)
                minutes = int((float(date_delay) - float(hours)) * float(60))
                date_start = date_stop - datetime.timedelta(hours=hours, minutes=minutes)
                res[obj.id] = date_start
        return res

    _columns = {
        'worked_hours': fields.function(_worked_hours_compute, type='float', string='Worked Hours', store=True),
        'calendar_start': fields.function(_calendar_start, type='datetime', string='Calendar start', store=True),
    }


class tempo_hr_plan(osv.osv):
    _name = "tempo_hr"

    def cron_plan_tempo_hr(self, cr, uid, context=None):
        hr_tempo = self.pool.get('tempo_hr')
        ids = hr_tempo.search(cr, uid, [], context=context)
        hr_tempo.unlink(cr, uid, ids, context=context)

        employees = self.pool.get('hr.employee')\
            .search(cr, uid,
                    ['|', ('active', '=', False),
                     ('active', '=', True)])
        for employee in self.pool.get('hr.employee').browse(cr, uid, employees):
            print employee.name
            working_days = employee.contract_id\
                .working_hours.attendance_ids
            year_now = datetime.datetime.now().year
            current_date = datetime.date(year_now, 1, 1)
            date_stop = datetime.date(year_now + 1, 12, 31)
            if employee.tz is not False:
                tz = pytz.timezone(employee.tz)
            else:
                tz = pytz.utc
            if working_days is not None:
                while current_date <= date_stop:
                    holidays = self.pool.get('public.holidays.holidays')\
                        .is_holiday(cr, uid, current_date, employee=employee)
                    if holidays is False:
                        for day in working_days:
                            if int(day.dayofweek) == current_date.weekday():
                                time_in = str(day.hour_from).split('.')
                                date_in = str(current_date) + " "
                                date_in += str(time_in[0]) + ":"
                                if len(str(time_in[1])) == 1:
                                    date_in += "0" + str(time_in[1])
                                else:
                                    date_in += str(time_in[1])
                                name_in = datetime.datetime\
                                    .strptime(date_in, '%Y-%m-%d %H:%M')
                                date_in = tz.localize(name_in, is_dst=None)
                                dateIn = date_in.astimezone(pytz.utc)

                                time_out = str(day.hour_to).split('.')
                                date_out = str(current_date) + " "
                                date_out += str(time_out[0]) + ":"
                                if len(str(time_out[1])) == 1:
                                    date_out += "0" + str(time_out[1])
                                else:
                                    date_out += str(time_out[1])
                                name_out = datetime.datetime\
                                    .strptime(date_out, '%Y-%m-%d %H:%M')
                                date_out = tz.localize(name_out, is_dst=None)
                                dateOut = date_out.astimezone(pytz.utc)

                                print "DATe : "
                                print dateIn
                                print dateOut
                                vals = {
                                    'employee_id': employee.id,
                                    'date_start': dateIn,
                                    'date_stop': dateOut,
                                }
                                hr_tempo = self.pool.get('tempo_hr')
                                hr_tempo.create(cr, uid, vals, context=context)
                    current_date = current_date + datetime.timedelta(days=1)

        return None

    _columns = {
        'employee_id': fields.many2one('hr.employee', "Employee", required=True),
        'date_start': fields.datetime('Start Date', required=True),
        'date_stop': fields.datetime('End Date', required=True),
    }