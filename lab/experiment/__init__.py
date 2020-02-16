import os
import pathlib
import time
from typing import Optional, List, Set, Dict, Union

import git

from lab import logger
from lab.configs import Configs, ConfigProcessor
from lab.experiment.experiment_run import Run
from lab.lab import Lab
from lab.logger.colors import Text
from lab.logger.internal import CheckpointSaver
from lab.logger.writers import sqlite, tensorboard
from lab.util import is_ipynb


class Experiment:
    """
    ## Experiment

    Each experiment has different configurations or algorithms.
    An experiment can have multiple trials.
    """
    run: Run
    configs_processor: Optional[ConfigProcessor]

    # whether not to start the experiment if there are uncommitted changes.
    check_repo_dirty: bool

    def __init__(self, *,
                 name: Optional[str],
                 python_file: Optional[str],
                 comment: Optional[str],
                 writers: Set[str] = None,
                 ignore_callers: Set[str] = None):
        """
        ### Create the experiment

        :param name: name of the experiment
        :param python_file: `__file__` that invokes this. This is stored in
         the experiments list.
        :param comment: a short description of the experiment

        The experiments log keeps track of `python_file`, `name`, `comment` as
         well as the git commit.

        Experiment maintains the locations of checkpoints, logs, etc.
        """

        if python_file is None:
            python_file = self.__get_caller_file(ignore_callers)

        if python_file.startswith('<ipython'):
            assert is_ipynb()
            if name is None:
                raise ValueError("You must specify python_file or experiment name"
                                 " when creating an experiment from a python notebook.")
            self.lab = Lab(os.getcwd())
            python_file = 'notebook.ipynb'
        else:
            self.lab = Lab(python_file)

            if name is None:
                file_path = pathlib.PurePath(python_file)
                name = file_path.stem

        logger.internal().set_data_path(self.lab.data_path)

        if comment is None:
            comment = ''

        self.name = name
        self.experiment_path = self.lab.experiments / name

        self.check_repo_dirty = self.lab.check_repo_dirty

        self.configs_processor = None

        experiment_path = pathlib.Path(self.experiment_path)
        if not experiment_path.exists():
            experiment_path.mkdir(parents=True)

        self.run = Run.create(
            experiment_path=self.experiment_path,
            python_file=python_file,
            trial_time=time.localtime(),
            comment=comment)

        repo = git.Repo(self.lab.path)

        self.run.commit = repo.head.commit.hexsha
        self.run.commit_message = repo.head.commit.message.strip()
        self.run.is_dirty = repo.is_dirty()
        self.run.diff = repo.git.diff()

        checkpoint_saver = self._create_checkpoint_saver()
        logger.internal().set_checkpoint_saver(checkpoint_saver)

        if writers is None:
            writers = {'sqlite', 'tensorboard'}

        if 'sqlite' in writers:
            logger.internal().add_writer(sqlite.Writer(self.run.sqlite_path))
        if 'tensorboard' in writers:
            logger.internal().add_writer(tensorboard.Writer(self.run.tensorboard_log_path))

        logger.internal().set_numpy_path(self.run.numpy_path)

    @staticmethod
    def __get_caller_file(ignore_callers: Set[str] = None):
        if ignore_callers is None:
            ignore_callers = {}

        import inspect

        frames: List[inspect.FrameInfo] = inspect.stack()
        lab_src = pathlib.PurePath(__file__).parent.parent

        for f in frames:
            module_path = pathlib.PurePath(f.filename)
            if str(module_path).startswith(str(lab_src)):
                continue
            if str(module_path) in ignore_callers:
                continue
            return str(module_path)

        return ''

    def _create_checkpoint_saver(self) -> Optional[CheckpointSaver]:
        return None

    def __print_info_and_check_repo(self):
        """
        ## 🖨 Print the experiment info and check git repo status
        """

        logger.new_line()
        logger.log([
            (self.name, Text.title),
            ': ',
            (str(self.run.uuid), Text.meta)
        ])

        if self.run.comment != '':
            logger.log(['\t', (self.run.comment, Text.highlight)])

        logger.log([
            "\t"
            "[dirty]" if self.run.is_dirty else "[clean]",
            ": ",
            (f"\"{self.run.commit_message.strip()}\"", Text.highlight)
        ])

        # Exit if git repository is dirty
        if self.check_repo_dirty and self.run.is_dirty:
            logger.log([("[FAIL]", Text.danger),
                        " Cannot trial an experiment with uncommitted changes."])
            exit(1)

    def _load_checkpoint(self, checkpoint_path: pathlib.PurePath):
        raise NotImplementedError()

    def calc_configs(self,
                     configs: Optional[Configs],
                     configs_dict: Dict[str, any] = None,
                     run_order: Optional[List[Union[List[str], str]]] = None):
        if configs_dict is None:
            configs_dict = {}
        self.configs_processor = ConfigProcessor(configs, configs_dict)
        self.configs_processor(run_order)
        logger.new_line()

    def __start_from_checkpoint(self, run_uuid: Optional[str], checkpoint: int):
        checkpoint_path, global_step = experiment_run.get_last_run_checkpoint(
            self.experiment_path,
            run_uuid,
            checkpoint,
            {self.run.uuid})

        if global_step is None:
            return 0
        else:
            with logger.section("Loading checkpoint"):
                self._load_checkpoint(checkpoint_path)

        return global_step

    def start(self, *,
              run_uuid: Optional[str] = None,
              checkpoint: Optional[int] = None):
        if run_uuid is not None:
            if checkpoint is None:
                checkpoint = -1
            if run_uuid == '':
                run_uuid = None
            global_step = self.__start_from_checkpoint(run_uuid, checkpoint)
        else:
            global_step = 0

        self.run.start_step = global_step
        logger.internal().set_start_global_step(global_step)

        self.__print_info_and_check_repo()
        if self.configs_processor is not None:
            self.configs_processor.print()

        self.run.save_info()

        if self.configs_processor is not None:
            self.configs_processor.save(self.run.configs_path)

        logger.internal().save_indicators(self.run.indicators_path)
