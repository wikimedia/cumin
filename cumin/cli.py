#!/usr/bin/python3
"""Cumin CLI entry point."""
import argparse
import code
import json
import logging
import os
import pkgutil
import signal
import sys

from logging.handlers import RotatingFileHandler  # pylint: disable=ungrouped-imports

import colorama

from tqdm import tqdm

import cumin

from cumin import backends, query, transport, transports


logger = logging.getLogger(__name__)  # pylint: disable=invalid-name
"""logging.Logger: The logging instance."""
OUTPUT_FORMATS = ('txt', 'json')
"""tuple: A tuple with the possible output formats."""
OUTPUT_SEPARATOR = '_____FORMATTED_OUTPUT_____'
"""str: The output separator used when -o/--out is set."""
INTERACTIVE_BANNER = """===== Cumin Interactive REPL =====
# Press Ctrl+d or type exit() to exit the program.

= Available variables =
#     hosts: the ClusterShell NodeSet of targeted hosts.
#     worker: the instance of the Transport worker that was used for the execution.
#     args: the parsed command line arguments, an argparse.Namespace instance.
#     config: the cofiguration dictionary.
#     exit_code: the return code of the execution, that will be used as exit code.

= Useful functions =
#     worker.get_results(): generator that yields the tuple (nodes, output) for each grouped result, where:
#                         -     nodes: is a ClusterShell.NodeSet.NodeSet instance
#                         -     output: is a ClusterShell.MsgTree.MsgTreeElem instance
#     h(): print this help message.
#     help(object): Python default interactive help and documentation of the given object.

= Example usage:
for nodes, output in worker.get_results():
    print(nodes)
    print(output.message().decode())
    print('-----')
"""
"""str: The message to print when entering the intractive REPL mode."""


class KeyboardInterruptError(cumin.CuminError):
    """Custom KeyboardInterrupt exception class for the SIGINT signal handler."""


def get_parser():
    """Create and return the command line arguments parser.

    Returns:
        argparse.ArgumentParser: the parser object.

    """
    sync_mode = 'sync'
    async_mode = 'async'

    # Get the list of existing backends and transports
    backends_names = [name for _, name, ispkg in pkgutil.iter_modules(backends.__path__) if not ispkg]
    transports_names = [name for _, name, ispkg in pkgutil.iter_modules(transports.__path__) if not ispkg]

    parser = argparse.ArgumentParser(
        prog='cumin',
        description='Cumin CLI - Automation and orchestration framework written in Python',
        epilog='More details at https://wikitech.wikimedia.org/wiki/Cumin')
    parser.add_argument('-c', '--config', default='/etc/cumin/config.yaml',
                        help='configuration file. [default: /etc/cumin/config.yaml]')
    parser.add_argument('--global-timeout', type=int,
                        help='Global timeout in seconds (int) for the whole execution. [default: None (unlimited)]')
    parser.add_argument('-t', '--timeout', type=int,
                        help=('Timeout in seconds (int) for the the execution of every command in each host. '
                              '[default: None (unlimited)]'))
    parser.add_argument('-m', '--mode', choices=(sync_mode, async_mode),
                        help=('Execution mode, required when there are multiple COMMANDS to be executed. In sync mode, '
                              'execute the first command on all hosts, then proceed with the next one only if '
                              '-p/--success-percentage is reached. In async mode, execute on each host independently '
                              'from each other, the list of commands, aborting the execution on any given host at the '
                              'first command that fails.'))
    parser.add_argument('-p', '--success-percentage', type=int, choices=range(101), metavar='PCT', default=100,
                        help=(('Percentage threshold to consider an execution unit successful. Required in sync mode, '
                               'optional in async mode when -b/--batch-size is used. Accepted values are integers '
                               'in the range 0-100. [default: 100]')))
    parser.add_argument('-b', '--batch-size', type=target_batch_size, default={'value': None, 'ratio': None},
                        help=('The commands will be executed with a sliding batch of this size. The batch mode depends '
                              'on the -m/--mode option when multiple commands are specified. In sync mode the first '
                              'command is executed in batch to all hosts before proceeding with the next one. In async '
                              'mode all commands are executed on the first batch of hosts, proceeding with the next '
                              'hosts as soon as one host completes all the commands. The -p/--success-percentage is '
                              'checked before starting the execution in each host. It accept an absolute integer '
                              '(i.e. 10) or a percentage (i.e. 50%%). [default: None (# of hosts)]'))
    parser.add_argument('-s', '--batch-sleep', type=float,
                        help=('Sleep in seconds (float) to wait before starting the execution on the next host when '
                              '-b/--batch-size is used. [default: None]'))
    parser.add_argument('-x', '--ignore-exit-codes', action='store_true',
                        help=('USE WITH CAUTION! Treat any executed command as successful, ignoring the exit codes. '
                              '[default: False]'))
    parser.add_argument('-o', '--output', choices=OUTPUT_FORMATS,
                        help='Specify a different output format. [default: None]')
    parser.add_argument('-i', '--interactive', action='store_true',
                        help='Drop into a Python shell with the results. [default: False]')
    parser.add_argument('--force', action='store_true',
                        help=('USE WITH CAUTION! Force the execution without confirmation of the affected hosts. '
                              '[default: False]'))
    parser.add_argument('--backend',
                        help=('Override the default backend selected in the configuration file for this execution. The '
                              'backend-specific configuration must be already present in the configuration file. '
                              'One of [{backends}] or any external backend listed in the configuration file '
                              '[default: None]').format(backends=', '.join(backends_names)))
    parser.add_argument('--transport', choices=transports_names,
                        help=('Override the default transport selected in the configuration file for this execution. '
                              'The transport-specific configuration must already be present in the configuration file. '
                              '[default: None]'))
    parser.add_argument('--dry-run', action='store_true',
                        help=('Do not execute any command, just return the list of matching hosts and exit. '
                              '[default: False]'))
    parser.add_argument('--version', action='version', version='%(prog)s {version}'.format(version=cumin.__version__))
    parser.add_argument('-d', '--debug', action='store_true', help='Set log level to DEBUG. [default: False]')
    parser.add_argument('--trace', action='store_true',
                        help=('Set log level to TRACE, a custom logging level intended for development debugging. '
                              '[default: False]'))
    parser.add_argument('hosts', metavar='HOSTS_QUERY', help='Hosts selection query')
    parser.add_argument('commands', metavar='COMMAND', nargs='*',
                        help='Command to be executed. If no commands are specified, --dry-run is set.')

    return parser


def target_batch_size(string):
    """Validator for the --batch-size command line argument to be used as type in ArgumentParser.

    Arguments:
        string: the input string to be validated and parsed.

    Returns:
        dict: a dictionary with the batch size absolute value as integer (`value` key) or the ratio value as float
            (`ratio` key) to be used when instantiating a Target object.

    """
    is_percentage = False
    orig = string
    if string[-1] == '%':
        is_percentage = True
        string = string[:-1]

    value = int(string)
    if is_percentage and not (0 <= value <= 100):  # pylint: disable=superfluous-parens
        raise argparse.ArgumentTypeError(
            '{size} is not a valid percentage, expected in range 0%-100% or positive integer.'.format(size=orig))

    if not is_percentage and value <= 0:
        raise argparse.ArgumentTypeError(
            '{size} is not a valid value, expected positive integer or percentage in range 0%-100%'.format(size=orig))

    ret = {'value': None, 'ratio': None}
    if is_percentage:
        ret['ratio'] = value / 100
    else:
        ret['value'] = value

    return ret


def parse_args(argv):
    """Parse command line arguments, validate and return them.

    Arguments:
        argv: the list of command line arguments to use.

    Returns:
        argparse.Namespace: the parsed arguments.

    """
    parser = get_parser()
    parsed_args = parser.parse_args(argv)

    # Validation and default values
    num_commands = len(parsed_args.commands)
    if num_commands == 0:
        parsed_args.dry_run = True
    elif num_commands == 1:
        parsed_args.mode = 'sync'
    elif num_commands > 1:
        if parsed_args.mode is None:
            parser.error('-m/--mode is required when there are multiple COMMANDS')
        if parsed_args.interactive:
            parser.error('-i/--interactive can be used only with one command')
        if parsed_args.output is not None:
            parser.error('-o/--output can be used only with one command')

    if parsed_args.ignore_exit_codes:
        stderr('IGNORE EXIT CODES mode enabled, all commands executed will be considered successful')

    return parsed_args


def get_running_user():
    """Ensure it's running as root and that the original user is detected and return it."""
    if os.getenv('USER') != 'root':
        raise cumin.CuminError('Insufficient privileges, run with sudo')
    if os.getenv('SUDO_USER') in (None, 'root'):
        raise cumin.CuminError('Unable to determine real user, logged in as root?')

    return os.getenv('SUDO_USER')


def setup_logging(filename, debug=False, trace=False):
    """Setup the logger instance.

    Arguments:
        filename: the filename of the log file
        debug: whether to set logging level to DEBUG [optional, default: False]
    """
    file_path = os.path.dirname(filename)
    if file_path and not os.path.exists(file_path):
        os.makedirs(file_path, 0o770)

    log_formatter = logging.Formatter(fmt='%(asctime)s [%(levelname)s %(process)s %(name)s.%(funcName)s] %(message)s')
    log_handler = RotatingFileHandler(filename, maxBytes=(5 * (1024**2)), backupCount=30)
    log_handler.setFormatter(log_formatter)

    root_logger = logging.getLogger()
    root_logger.addHandler(log_handler)
    root_logger.raiseExceptions = False

    if trace:
        root_logger.setLevel(cumin.LOGGING_TRACE_LEVEL_NUMBER)
    elif debug:
        root_logger.setLevel(logging.DEBUG)
    else:
        root_logger.setLevel(logging.INFO)


def sigint_handler(*args):  # pylint: disable=unused-argument
    """Signal handler for Ctrl+c / SIGINT, raises KeyboardInterruptError.

    Arguments (as defined in https://docs.python.org/3/library/signal.html):
        signum: the signal number
        frame: the current stack frame
    """
    if not sys.stdout.isatty():  # pylint: disable=no-member
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
    #         answer = input('\n')  # nosec
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
    #     logger.warning('Execution interrupted by Ctrl+c/SIGINT: got invalid answer for %d times', i)
    #     raise KeyboardInterruptError


def stderr(message, end='\n'):
    r"""Print a message to stderr and flush.

    Arguments:
        message: the message to print to sys.stderr
        end: the character to use at the end of the message. [optional, default: \n]
    """
    tqdm.write('{color}{message}{reset}'.format(
        color=colorama.Fore.YELLOW, message=message, reset=colorama.Style.RESET_ALL), file=sys.stderr, end=end)


def get_hosts(args, config):
    """Resolve the hosts selection into a list of hosts and return it. Raises KeyboardInterruptError.

    Arguments:
        args: ArgumentParser instance with parsed command line arguments
        config: a dictionary with the parsed configuration file
    """
    hosts = query.Query(config).execute(args.hosts)

    if not hosts:
        stderr('No hosts found that matches the query')
        return hosts

    stderr('{num} hosts will be targeted:'.format(num=len(hosts)))
    stderr('{color}{hosts}'.format(color=colorama.Fore.CYAN, hosts=cumin.nodeset_fromlist(hosts)))

    if args.dry_run:
        stderr('DRY-RUN mode enabled, aborting')
        return []
    elif args.force:
        stderr('FORCE mode enabled, continuing without confirmation')
        return hosts
    elif not sys.stdout.isatty():  # pylint: disable=no-member
        message = 'Not in a TTY but neither DRY-RUN nor FORCE mode were specified.'
        stderr(message)
        raise cumin.CuminError(message)

    for i in range(10):
        stderr('Confirm to continue [y/n]?', end=' ')
        answer = input()  # nosec
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


def print_output(output_format, worker):
    """Print the execution results in a specific format.

    Arguments:
        output_format: the output format to use, one of: 'txt', 'json'.
        worker: the Transport worker instance to retrieve the results from.
    """
    if output_format not in OUTPUT_FORMATS:
        raise cumin.CuminError("Got invalid output format '{fmt}', expected one of {allowed}".format(
            fmt=output_format, allowed=OUTPUT_FORMATS))

    out = {}
    for nodeset, output in worker.get_results():
        for node in nodeset:
            if output_format == 'txt':
                out[node] = '\n'.join('{node}: {line}'.format(node=node, line=line.decode()) for line in output.lines())
            elif output_format == 'json':
                out[node] = output.message().decode()

    if output_format == 'txt':
        for node in sorted(out.keys()):
            tqdm.write(out[node])
    elif output_format == 'json':
        tqdm.write(json.dumps(out, indent=4, sort_keys=True))


def run(args, config):
    """Execute the commands on the selected hosts and print the results.

    Arguments:
        args: ArgumentParser instance with parsed command line arguments
        config: a dictionary with the parsed configuration file
    """
    hosts = get_hosts(args, config)
    if not hosts:
        return 0

    target = transports.Target(hosts, batch_size=args.batch_size['value'], batch_size_ratio=args.batch_size['ratio'],
                               batch_sleep=args.batch_sleep)
    worker = transport.Transport.new(config, target)

    ok_codes = None
    if args.ignore_exit_codes:
        ok_codes = []

    worker.commands = [transports.Command(command, timeout=args.timeout, ok_codes=ok_codes)
                       for command in args.commands]
    worker.timeout = args.global_timeout
    worker.handler = args.mode
    worker.success_threshold = args.success_percentage / 100
    exit_code = worker.execute()

    if args.interactive:
        # Define a help function h() that will be available in the interactive shell to print the help message.
        # The name is to not shadow the Python built-in help() that might be usefult too to inspect objects.
        def h():  # pylint: disable=unused-variable,invalid-name
            """Print the help message in interactive shell."""
            tqdm.write(INTERACTIVE_BANNER)
        code.interact(banner=INTERACTIVE_BANNER, local=locals())
    elif args.output is not None:
        tqdm.write(OUTPUT_SEPARATOR)
        print_output(args.output, worker)

    return exit_code


def validate_config(config):
    """Perform validation of mandatory keys in the configuration.

    Arguments:
        config (dict): the loaded configuration to validate.

    Raises:
        cumin.CuminError: if a mandatory configuration key is missing.

    """
    if 'log_file' not in config:
        raise cumin.CuminError("Missing required parameter 'log_file' in the configuration file '{config}'".format(
            config=config))


def main(argv=None):
    """CLI entry point. Execute commands on hosts according to arguments.

    Arguments:
        argv: the list of command line arguments to use. If not specified it will be automatically taken from sys.argv
            [optional, default: None]
    """
    if argv is None:
        argv = sys.argv[1:]

    signal.signal(signal.SIGINT, sigint_handler)
    colorama.init()

    # Setup
    try:
        args = parse_args(argv)
        user = get_running_user()
        config = cumin.Config(args.config)
        validate_config(config)
        setup_logging(config['log_file'], debug=args.debug, trace=args.trace)
    except cumin.CuminError as e:
        stderr(e)
        return 2
    except Exception as e:  # pylint: disable=broad-except
        stderr('Caught {name} exception: {msg}'.format(name=e.__class__.__name__, msg=e))
        return 3

    # Override config with command line arguments
    if args.backend is not None:
        config['default_backend'] = args.backend
    if args.transport is not None:
        config['transport'] = args.transport

    logger.info("Cumin called by user '%s' with args: %s", user, args)

    # Execution
    try:
        exit_code = run(args, config)
    except KeyboardInterruptError:
        stderr('Execution interrupted by Ctrl+c/SIGINT/Aborted')
        exit_code = 98
    except Exception as e:  # pylint: disable=broad-except
        stderr('Caught {name} exception: {msg}'.format(name=e.__class__.__name__, msg=e))
        logger.exception('Failed to execute')
        exit_code = 99

    return exit_code


if __name__ == '__main__':
    sys.exit(main())
