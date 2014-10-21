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
    # put POSIX 'Etc/*' entries at the end to avoid confusing users - see bug 1086728
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

    def _calc_tempo_duration(self, cr, uid, ids, field_name, arg, context):
        res = {}
        record = self.browse(cr, uid, ids, context=context)
        for data in record:

            if data.action == "sign_in":
                res[data.id] = ''
            else:
                last_signin_id = self.search(cr, uid, [
                    ('employee_id', '=', data.employee_id.id),
                    ('name', '<', data.name), ('action', '=', 'sign_in')
                ], limit=1, order='name DESC')

                if last_signin_id:
                    last_signin = self.browse(cr, uid, last_signin_id,
                                              context=context)[0]
                    last_signin_time = datetime.datetime\
                        .strptime(last_signin.name, '%Y-%m-%d %H:%M:%S')
                    signout_time = datetime.datetime\
                        .strptime(data.name, '%Y-%m-%d %H:%M:%S')
                    workedhours_datetime = (signout_time - last_signin_time)
                    seconds = workedhours_datetime.seconds % 60
                    if seconds < 10:
                        seconds = "0" + str(seconds)
                    minutes = (workedhours_datetime.seconds / 60) % 60
                    if minutes < 10:
                        minutes = "0" + str(minutes)
                    hours = (workedhours_datetime.seconds / 60) / 60
                    if hours < 10:
                        hours = "0" + str(hours)
                    res[data.id] = str(hours) + ":" + str(minutes) + ":" + str(seconds)
                else:
                    res[data.id] = ''

        return res

    _columns = {
        'duration': fields.function(_calc_tempo_duration,
        string="Duration",
        type="text")
    }
