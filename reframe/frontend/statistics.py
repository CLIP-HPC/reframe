# Copyright 2016-2020 Swiss National Supercomputing Centre (CSCS/ETH Zurich)
# ReFrame Project Developers. See the top-level LICENSE file for details.
#
# SPDX-License-Identifier: BSD-3-Clause
import json

import reframe.core.debug as debug
import reframe.core.runtime as rt
from reframe.core.exceptions import format_exception, StatisticsError


class TestStats:
    '''Stores test case statistics.'''

    def __init__(self):
        # Tasks per run stored as follows: [[run0_tasks], [run1_tasks], ...]
        self._alltasks = [[]]

    def __repr__(self):
        return debug.repr(self)

    def add_task(self, task):
        current_run = rt.runtime().current_run
        if current_run == len(self._alltasks):
            self._alltasks.append([])

        self._alltasks[current_run].append(task)

    def tasks(self, run=-1):
        try:
            return self._alltasks[run]
        except IndexError:
            raise StatisticsError('no such run: %s' % run) from None

    def failures(self, run=-1):
        return [t for t in self.tasks(run) if t.failed]

    def num_cases(self, run=-1):
        return len(self.tasks(run))

    def retry_report(self):
        # Return an empty report if no retries were done.
        if not rt.runtime().current_run:
            return ''

        line_width = 78
        report = [line_width * '=']
        report.append('SUMMARY OF RETRIES')
        report.append(line_width * '-')
        messages = {}

        for run in range(1, len(self._alltasks)):
            for t in self.tasks(run):
                partition_name = ''
                environ_name = ''
                if t.check.current_partition:
                    partition_name = t.check.current_partition.fullname

                if t.check.current_environ:
                    environ_name = t.check.current_environ.name

                key = '%s:%s:%s' % (t.check.name, partition_name, environ_name)
                # Overwrite entry from previous run if available
                messages[key] = (
                    '  * Test %s was retried %s time(s) and %s.' %
                    (t.check.info(), run, 'failed' if t.failed else 'passed')
                )

        for key in sorted(messages.keys()):
            report.append(messages[key])

        return '\n'.join(report)

    def json(self):
        records = []
        current_run = rt.runtime().current_run
        for run_no, run in enumerate(self._alltasks):
            for t in run:
                check = t.check
                partition = check.current_partition
                partfullname = partition.fullname if partition else None
                environ_name = (check.current_environ.name
                                if check.current_environ else None)
                entry = {
                    'testname': check.name,
                    'description': check.descr,
                    'system': partfullname,
                    'environment': environ_name,
                    'tags': list(check.tags),
                    'maintainers': check.maintainers,
                    'scheduler': None,
                    'jobid': None,
                    'nodelist': [],
                    'job_stdout': None,
                    'job_stderr': None,
                    'build_stdout': None,
                    'build_stderr': None,
                    'failing_reason': None,
                    'failing_phase': None,
                    'outputdir': None,
                    'stagedir': None,
                    'job_stdout': None,
                    'job_stderr': None
                }
                if check.job:
                    entry['scheduler'] = partition.scheduler.registered_name
                    entry['jobid'] = check.job.jobid
                    entry['nodelist'] = check.job.nodelist or []
                    entry['job_stdout'] = check.stdout.evaluate()
                    entry['job_stderr'] = check.stderr.evaluate()

                if check._build_job:
                    entry['build_stdout'] = check.build_stdout.evaluate()
                    entry['build_stderr'] = check.build_stderr.evaluate()

                if t.failed:
                    entry['result'] = 'fail'
                    if t.exc_info is not None:
                        entry['failing_reason'] = format_exception(
                            *t.exc_info)
                        entry['failing_phase'] = t.failed_stage
                        entry['stagedir'] = check.stagedir
                else:
                    entry['result'] = 'success'
                    entry['outputdir'] = check.outputdir

                entry['run_no'] = run_no

                records.append(entry)

        return records

    def json_report(self):
        with open('report.json', 'w') as fp:
            json.dump(self.json(), fp, indent=4)

    def failure_report(self):
        line_width = 78
        report = [line_width * '=']
        report.append('SUMMARY OF FAILURES')
        last_run = rt.runtime().current_run
        for r in self.json():
            if r['result'] == 'success' or r['run_no'] != last_run:
                continue
            retry_info = ('(for the last of %s retries)' % last_run
                          if last_run > 0 else '')
            report.append(line_width * '-')
            report.append('FAILURE INFO for %s %s' % (r['testname'],
                                                      retry_info))
            report.append('  * Test Description: %s' % r['description'])
            report.append('  * System partition: %s' % r['system'])
            report.append('  * Environment: %s' % r['environment'])
            report.append('  * Stage directory: %s' % r['stagedir'])
            report.append('  * Node list: %s' %
                          (','.join(r['nodelist'])
                           if r['nodelist'] else None))
            job_type = 'local' if r['scheduler'] == 'local' else 'batch job'
            jobid = r['jobid']
            report.append('  * Job type: %s (id=%s)' % (job_type, jobid))
            report.append('  * Maintainers: %s' % r['maintainers'])
            report.append('  * Failing phase: %s' % r['failing_phase'])
            report.append("  * Rerun with '-n %s -p %s --system %s'" %
                          (r['testname'], r['environment'], r['system']))
            report.append("  * Reason: %s" % r['failing_reason'])

            if r['failing_phase'] == 'sanity':
                report.append('Sanity check failure')
            elif r['failing_phase'] == 'performance':
                report.append('Performance check failure')
            else:
                # This shouldn't happen...
                report.append('Unknown error.')

        report.append(line_width * '-')
        return '\n'.join(report)

    def failure_stats(self):
        failures = {}
        current_run = rt.runtime().current_run
        for tf in (t for t in self.tasks(current_run) if t.failed):
            check = tf.check
            partition = check.current_partition
            partfullname = partition.fullname if partition else 'None'
            environ_name = (check.current_environ.name
                            if check.current_environ else 'None')
            f = f'[{check.name}, {environ_name}, {partfullname}]'
            if tf.failed_stage not in failures:
                failures[tf.failed_stage] = []

            failures[tf.failed_stage].append(f)

        line_width = 78
        stats_start = line_width * '='
        stats_title = 'FAILURE STATISTICS'
        stats_end = line_width * '-'
        stats_body = []
        row_format = "{:<13} {:<5} {}"
        stats_hline = row_format.format(13*'-', 5*'-', 60*'-')
        stats_header = row_format.format('Phase', '#', 'Failing test cases')
        num_tests = len(self.tasks(current_run))
        num_failures = 0
        for l in failures.values():
            num_failures += len(l)

        stats_body = ['']
        stats_body.append('Total number of test cases: %s' % num_tests)
        stats_body.append('Total number of failures: %s' % num_failures)
        stats_body.append('')
        stats_body.append(stats_header)
        stats_body.append(stats_hline)
        for p, l in failures.items():
            stats_body.append(row_format.format(p, len(l), l[0]))
            for f in l[1:]:
                stats_body.append(row_format.format('', '', str(f)))

        if stats_body:
            return '\n'.join([stats_start, stats_title, *stats_body,
                              stats_end])
        return ''

    def performance_report(self):
        line_width = 78
        report_start = line_width * '='
        report_title = 'PERFORMANCE REPORT'
        report_end = line_width * '-'
        report_body = []
        previous_name = ''
        previous_part = ''
        for t in self.tasks():
            if t.check.perfvalues.keys():
                if t.check.name != previous_name:
                    report_body.append(line_width * '-')
                    report_body.append('%s' % t.check.name)
                    previous_name = t.check.name

                if t.check.current_partition.fullname != previous_part:
                    report_body.append(
                        '- %s' % t.check.current_partition.fullname)
                    previous_part = t.check.current_partition.fullname

                report_body.append('   - %s' % t.check.current_environ)
                report_body.append('      * num_tasks: %s' % t.check.num_tasks)

            for key, ref in t.check.perfvalues.items():
                var = key.split(':')[-1]
                val = ref[0]
                try:
                    unit = ref[4]
                except IndexError:
                    unit = '(no unit specified)'

                report_body.append('      * %s: %s %s' % (var, val, unit))

        if report_body:
            return '\n'.join([report_start, report_title, *report_body,
                              report_end])

        return ''
