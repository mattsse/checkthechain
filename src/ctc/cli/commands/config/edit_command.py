import os
import subprocess

from ctc import config_utils


def get_command_spec():
    return {
        'f': edit_config_command,
    }


def edit_config_command():
    editor = os.environ.get('EDITOR')
    if editor is None or editor == '':
        raise Exception('set $EDITOR env var')

    config_path = config_utils.get_config_path()

    print('editing config in editor')
    print('- editor:', editor)
    print('- config_path:', config_path)
    print()
    subprocess.call([editor, config_path])
    print('done editing config')
