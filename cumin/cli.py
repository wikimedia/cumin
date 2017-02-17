#!/usr/bin/python2
"""
Cumin CLI entry point
"""

import argparse
import logging
import os
import pkgutil
import signal
import sys

from logging.handlers import RotatingFileHandler

import colorama
import yaml

from ClusterShell.NodeSet import NodeSet
from tqdm import tqdm

from cumin.query import QueryBuilder
from cumin.transport import Transport

logger = logging.getLogger(__name__)


class KeyboardInterruptError(Exception):
    """Custom KeyboardInterrupt exception class for the SIGINT signal handler"""


def parse_args(argv=None):
    """ Parse command line arguments and return them

        Arguments:
        argv -- the list of arguments to use. If None, the command line ones are used [optional, default: None]
    """
    sync_mode = 'sync'
    async_mode = 'async'

    # Get the list of existing backends and transports
    abs_path = os.path.dirname(os.path.abspath(__file__))
    backends = [name for _, name, _ in pkgutil.iter_modules([os.path.join(abs_path, 'backends')])]
    transports = [name for _, name, _ in pkgutil.iter_modules([os.path.join(abs_path, 'transports')])]

    parser = argparse.ArgumentParser(
        description='Cumin CLI - An automation and orchestration tool',
        epilog='More details at https://wikitech.wikimedia.org/wiki/Cumin')
    parser.add_argument('-c', '--config', default='/etc/cumin/config.yaml',
                        help='configuration file. [default: /etc/cumin/config.yaml]')
    parser.add_argument('-t', '--timeout', type=int, help='timeout in seconds. [default: 0 (unlimited)]', default=0)
    parser.add_argument('-m', '--mode', choices=(sync_mode, async_mode),
                        help=('Execution mode, required when there are multiple COMMANDS to be executed. In sync mode, '
                              'execute the first command on all hosts, then proceed with the next one only if '
                              '-s/--success-percentage is reached. In async mode, execute on each host independently '
                              'from each other, the list of commands, aborting the execution on any given host at the '
                              'first command that fails.'))
    parser.add_argument('-s', '--success-percentage', type=int, choices=xrange(101), metavar='0-100',
                        help=(('Percentage threshold to consider an execution unit successful. Used only when in sync '
                               'mode and there are multiple COMMANDS. [default: 100]')))
    parser.add_argument('--force', action='store_true',
                        help='force the execution without confirmation of the affected hosts')
    parser.add_argument('--backend', choices=backends,
                        help=('backend to be used for hosts selection. The backend configuration must be present in '
                              'the configuration file.'))
    parser.add_argument('--transport', choices=transports,
                        help=('transport to be used for commands execution. The transport configuration must be '
                              'in the configuration file.'))
    parser.add_argument('--dry-run', action='store_true',
                        help='do not execute the commands, just return the list of hosts')
    parser.add_argument('-d', '--debug', action='store_true', help='set log level to DEBUG')
    parser.add_argument('hosts', metavar='HOSTS_QUERY', help='hosts selection query')
    parser.add_argument('commands', metavar='COMMAND', nargs='+', help='command to be executed')

    if argv is None:
        parsed_args = parser.parse_args()
    else:
        parsed_args = parser.parse_args(argv)

    # Validation

    if len(parsed_args.commands) > 1 and parsed_args.mode is None:
        parser.error('-m/--mode is required when there are multiple COMMANDS')

    if len(parsed_args.commands) == 1:
        if parsed_args.mode is not None:
            parser.error('-m/--mode cannot be specified with only one COMMAND')
        if parsed_args.success_percentage is not None:
            parser.error('-s/--success-percentage cannot be specified with only one COMMAND')

    if parsed_args.success_percentage is not None and parsed_args.mode == async_mode:
        parser.error("-s/--success-percentage cannot be specified when mode is '{mode}'".format(mode=async_mode))

    # Default values

    if parsed_args.success_percentage is None:
        parsed_args.success_percentage = 100

    return parsed_args


def get_running_user():
    """Ensure it's running as root and that the original user is detected and return it"""
    if os.getenv('USER') != 'root':
        raise RuntimeError('Unsufficient privileges, run with sudo')
    if os.getenv('SUDO_USER') in (None, 'root'):
        raise RuntimeError('Unable to determine real user')

    return os.getenv('SUDO_USER')


def setup_logging(user, filename, debug=False):
    """ Setup the logger instance

        Arguments:
        user     -- the real user to use in the logging formatter for auditing
        filename -- the filename of the log file
        debug    -- whether to set logging level to DEBUG [optional, default: False]
    """

    file_path = os.path.dirname(filename)
    if not os.path.exists(file_path):
        os.makedirs(file_path, 0770)

    log_formatter = logging.Formatter(
        fmt=('%(asctime)s [%(levelname)s] ({user}) %(name)s::%(funcName)s: %(message)s').format(user=user),
        datefmt='%F %T')
    log_handler = RotatingFileHandler(filename, maxBytes=(5 * (1024**2)), backupCount=30)
    log_handler.setFormatter(log_formatter)
    logger.addHandler(log_handler)
    logger.raiseExceptions = False

    if debug:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)


def parse_config(config_file):
    """ Parse the YAML configuration file

        Arguments:
        config_file -- the path of the configuration file to load
    """
    with open(config_file, 'r') as f:
        config = yaml.load(f)

    return config


def sigint_handler(signum, frame):
    """ Signal handler for Ctrl+c / SIGINT, raises KeyboardInterruptError

        Arguments (as defined in https://docs.python.org/2/library/signal.html):
        signum -- the signal number
        frame  -- the current stack frame
    """
    if not sys.stdout.isatty():
        logger.warning('Execution interrupted by Ctrl+c/SIGINT')
        raise KeyboardInterruptError

    # TODO: make the below code block to work as expected with ClusterShell
    #       temporarily exit upon Ctrl+c also in interactive mode
    logger.warning('Execution interrupted by Ctrl+c/SIGINT')
    raise KeyboardInterruptError
    # logger.warning('Received Ctrl+c/SIGINT')
    # for i in xrange(10):
    #     stderr('Ctrl+c pressed, sure to quit [y/n]?\n')
    #     try:
    #         answer = raw_input('\n')
    #     except RuntimeError:
    #         # Can't re-enter readline when already waiting for input in get_hosts(). Assuming 'y' as answer
    #         stderr('Ctrl+c pressed while waiting for answer. Aborting')
    #         answer = 'y'
    #
    #     if not answer:
    #         continue
    #
    #     if answer.lower() == 'y':
    #         logger.warning('Execution interrupted by Ctrl+c/SIGINT')
    #         raise KeyboardInterruptError
    #     elif answer.lower() == 'n':
    #         message = 'Ctrl+c/SIGINT aborted, resuming execution'
    #         logger.warning(message)
    #         stderr(message)
    #         break
    # else:
    #     logger.warning('Execution interrupted by Ctrl+c/SIGINT: got invalid answer for {i} times'.format(i=i))
    #     raise KeyboardInterruptError


def stderr(message, end='\n'):
    """ Print a message to stderr and flush

        Arguments:
        message -- the message to print to sys.stderr
        end     -- the character to use at the end of the message. [optional, default: \n]
    """
    tqdm.write('{color}{message}{reset}'.format(
        color=colorama.Fore.YELLOW, message=message, reset=colorama.Style.RESET_ALL), file=sys.stderr, end=end)


def get_hosts(args, config):
    """ Resolve the hosts selection into a list of hosts and return it. Raises KeyboardInterruptError

        Arguments:
        args   -- ArgumentParser instance with parsed command line arguments
        config -- a dictionary with the parsed configuration file
    """
    query = QueryBuilder(args.hosts, config, logger).build()
    hosts = query.execute()

    if len(hosts) == 0:
        stderr('No hosts found that matches the query')
        return hosts

    stderr('{num} hosts will be targeted:'.format(num=len(hosts)))
    stderr('{color}{hosts}'.format(color=colorama.Fore.CYAN, hosts=NodeSet.fromlist(hosts)))

    if args.dry_run:
        stderr('DRY-RUN mode enabled, aborting')
        return []
    elif args.force:
        stderr('FORCE mode enabled, continuing without confirmation')
        return hosts

    for i in xrange(10):
        stderr('Confirm to continue [y/n]?', end=' ')
        answer = raw_input()
        if not answer:
            continue

        if answer in 'yY':
            break
        elif answer in 'nN':
            raise KeyboardInterruptError

    else:
        stderr('Got invalid answer for {i} times'.format(i=i))
        raise KeyboardInterruptError

    return hosts


def run(args, config):
    """ Execute the commands on the selected hosts and print the results

        Arguments:
        args   -- ArgumentParser instance with parsed command line arguments
        config -- a dictionary with the parsed configuration file
    """
    hosts = get_hosts(args, config)
    if len(hosts) == 0:
        return

    transport = Transport.new(config, logger)
    transport.execute(hosts, args.commands, mode=args.mode, timeout=args.timeout, handler=True,
                      success_threshold=(args.success_percentage / float(100)))


def main(argv=None):
    """ CLI entry point. Execute commands on hosts according to arguments

        Arguments:
        argv -- the list of arguments to use. If None, the command line ones are used [optional, default: None]
    """
    signal.signal(signal.SIGINT, sigint_handler)
    colorama.init()

    # Setup
    try:
        args = parse_args(argv)
        user = get_running_user()
        config = parse_config(args.config)
        setup_logging(user, config['log_file'], debug=args.debug)
    except Exception as e:
        stderr('Caught {name} exception: {msg}'.format(name=e.__class__.__name__, msg=e))
        return 3

    # Override config with command line arguments
    if args.backend is not None:
        config['backend'] = args.backend
    if args.transport is not None:
        config['transport'] = args.transport

    logger.info('Cumin called with args: {}'.format(args))

    # Execution
    try:
        exit_code = 0
        run(args, config)
    except KeyboardInterruptError:
        stderr('Execution interrupted by Ctrl+c/SIGINT/Aborted')
        exit_code = 1
    except Exception as e:
        stderr('Caught {name} exception: {msg}'.format(name=e.__class__.__name__, msg=e))
        logger.exception('Failed to execute')
        exit_code = 2

    return exit_code


if __name__ == '__main__':
    """Execute the CLI"""
    sys.exit(main())
