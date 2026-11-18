"""Generated Silver Scripting classmethods; actual availability is checked by the vendor."""
from .api import Silver as SilverConnection

class Silver(SilverConnection):
    @classmethod
    def add_assignment(cls, assignment, *, session='default'):
        'Adds an assignment that will be execute at each step during modify_outputs.\n\nNote: all assignments will be removed when restart() is called.\n\nThis method is also available with the "runner" backend.\nReference: W-2024.09'
        return cls.call('add_assignment', assignment, session=session)

    @classmethod
    def add_module(cls, index=None, sil_line='', *, session='default', **kwargs):
        'Creates a new module.\n\nArgs:\n    sil_line: module configuration line.\n    index: the index where the module is to be added;\n        if left None, it will be added just before the GUI module.\n        If negative, the length of the list of modules will be added.\n        So adding at index -1 will result in adding the module\n        to be the penultimate. If index is greater than the length of\n        the modules list, the module will be added as the last element.\n        It is recommended to use sys.maxsize as index to add the module\n        to be the last.\n    kwargs any non-readonly module properties\nReturns:\n     the uuid of the new module\nReference: W-2024.09'
        return cls.call('add_module', index, sil_line, **kwargs, session=session)

    @classmethod
    def add_sfu(cls, index=None, path='', *, session='default', **kwargs):
        'Creates a new SFU.\n\nArgs:\n    path: path of the sil project to load as SFU.\n    index: the index where the SFU is to be added;\n        if left None, it will be added just before the GUI module.\n        If negative, the length of the list of modules will be added.\n        So adding at index -1 will result in adding the SFU\n        to be the penultimate. If index is greater than the length of\n        the modules list, the SFU will be added as the last element.\n        It is recommended to use sys.maxsize as index to add the SFU\n        to be the last.\n    kwargs any non-readonly SFU properties\nReturns:\n     the uuid of the new SFU\nReference: W-2024.09'
        return cls.call('add_sfu', index, path, **kwargs, session=session)

    @classmethod
    def add_tab(cls, tab_folder_uuid, index=None, *, session='default', **kwargs):
        "Creates a tab in the current Silver configuration,  under a  specified\ntab folder id.\n\nArgs:\n    tab_folder_uuid (str) : the tab folder  id  under  which the newly\n        created tab is added.\n    index (:obj:`int`, optional): the position of the  tab in the tabs\n        list. Affects  the  tab list  order.  Default  value  is None.\n        If index is None then the tab is added at the end of the list.\n    **kwargs: Arbitrary, any non-readonly tab properties.\n\nReturns:\n    str: The uuid of the newly created tab.\n\nRaises:\n    ValueError: If tab_folder_uuid does not exist.\n    IndexError: If index not between [0, tab list size].\n    TypeError: If property value is of incorrect type (eg. expecting\n    'int' received 'str').\nReference: W-2024.09"
        return cls.call('add_tab', tab_folder_uuid, index, **kwargs, session=session)

    @classmethod
    def add_tab_folder(cls, index=None, *, session='default', **kwargs):
        "Returns all the variables written by the module having the given uuid.\n\nCreates a tab folder in the current Silver configuration.\n\nArgs:\n    index (:obj:`int`, optional): the position of the  tab  folder  in\n        the tab  folder  list. Affects the tab folder  order.  Default\n        value is None. If index is None then the  tab  folder is added\n        at the end of the list.\n    **kwargs: Arbitrary, any non-readonly tab folder properties.\n\nReturns:\n    The  uuid  of  the  newly  created  tab  folder.\n\nRaises:\n    IndexError: If index not between [0, folder list size].\n    TypeError: If property value is of incorrect  type  (eg. expecting\n     'int' received 'str').\nReference: W-2024.09"
        return cls.call('add_tab_folder', index, **kwargs, session=session)

    @classmethod
    def clear(cls, working_dir=None, *, session='default'):
        'Clears project and changes directory if working_dir is not None.\nReference: W-2024.09'
        return cls.call('clear', working_dir, session=session)

    @classmethod
    def evaluate_expression(cls, expression, *, session='default'):
        'Evaluates the given expression and returns the result.\nReturns:\n    the result of the evaluation. Boolean values are represented as 0 and 1.\nReference: W-2024.09'
        return cls.call('evaluate_expression', expression, session=session)

    @classmethod
    def exit(cls, force=False, timeout=None, *, session='default'):
        'Exits Silver.\n\n        If script is run with --script argument, this function never\n        returns.\n\n        If script is run with remotesilverapi module, this function\n         returns when Silver was closed successfully.\n\n        This method is also available with the "runner" backend.\n\n        Args:\n            force: if True, Silver will be forcefully closed without\n                waiting for modules to finish (timeout argument is\n                ignored)\n            timeout: the time to wait for Silver to exit.\n                If None (default) or 0 the function will block until all \n                modules finish. In this case, if a module blocks in \n                an infinite loop or a deadlock, the method never returns.\n                If defined as positive number, Silver will begin the \n                exit procedures, but if it has still not stopped after \n                \'timeout\' seconds, the process will be closed as if \n                exit(force=True) had been called. This  argument is \n                ignored if force argument  is set to True.\nReference: W-2024.09'
        return cls.close(session=session, force=force, timeout=timeout)

    @classmethod
    def get_all_variable_names(cls, *, session='default'):
        'Returns an array containing the names of all Silver variables.\nReference: W-2024.09'
        return cls.call('get_all_variable_names', session=session)

    @classmethod
    def get_parameter_names(cls, *, session='default'):
        'Returns an array containing the names of all the variables that are\nflagged in at least one module with the PARAMETER flag.\nReference: W-2024.09'
        return cls.call('get_parameter_names', session=session)

    @classmethod
    def get_time(cls, *, session='default'):
        'Returns the Silver simulation time.\n\nThis method is also available with the "runner" backend.\nReference: W-2024.09'
        return cls.call('get_time', session=session)

    @classmethod
    def get_variable_names(cls, *, session='default'):
        'Returns an array containing the names of all the variables that are not\nflagged with the PARAMETER flag.\nReference: W-2024.09'
        return cls.call('get_variable_names', session=session)

    @classmethod
    def get_variable_value(cls, variable_name, *, session='default'):
        'Reads the value written by previous modules after all write_output\nfunctions have been called. This might not\nbe the persistent value that has been set with\n{@link #set_variable_value(String, Double)} if other modules\nwrite different value in write_outputs/modify_outputs.\n\nIf no module writes this variable, return None.\n\nThis method is also available with the "runner" backend.\nReference: W-2024.09'
        return cls.call('get_variable_value', variable_name, session=session)

    @classmethod
    def get_config_parameters(cls, *, session='default'):
        'Returns all the configuration parameters as a String to String Python\ndictionary.\nReference: W-2024.09'
        return cls.call('get_config_parameters', session=session)

    @classmethod
    def get_input_variables(cls, module_uuid, *, session='default'):
        'Returns all the variables read by the module having the given uuid.\nReference: W-2024.09'
        return cls.call('get_input_variables', module_uuid, session=session)

    @classmethod
    def get_modified_variables(cls, module_uuid, *, session='default'):
        'Returns all the variables modified by the module having the given uuid.\nReference: W-2024.09'
        return cls.call('get_modified_variables', module_uuid, session=session)

    @classmethod
    def get_module_properties(cls, module_uuid, *, session='default'):
        'Returns a dictionary containing all the module properties for the\nmodule having the given uuid. Some properties are read-only.\nIf a property is not defined, key will be mapped to None.\n\nNote: dictionary is not bound to the module.\nChanging the returned object has no effect on the module.\n\nList of editable properties: sil_line, preview_sil_line, parallel,\nremote(deprecated | use remote_cluster), remote_cluster, enabled,\nprefix, suffix, input_rename_rules_file, output_rename_rules_file,\nmodify_rename_rules_file, multiply_macro_step, macro_step_multiplier\nList of read-only properties: display_name, error_info, is_gui, comment\nReference: W-2024.09'
        return cls.call('get_module_properties', module_uuid, session=session)

    @classmethod
    def get_module_uuids(cls, *, session='default'):
        'Returns a list of uuids, one for each Silver module.\nList includes uuids for disabled modules.\nList includes uuids for modules that are part of an SFU.\nReference: W-2024.09'
        return cls.call('get_module_uuids', session=session)

    @classmethod
    def get_output_variables(cls, module_uuid, *, session='default'):
        'Returns all the variables written by the module having the given uuid.\nReference: W-2024.09'
        return cls.call('get_output_variables', module_uuid, session=session)

    @classmethod
    def get_project_properties(cls, *, session='default'):
        'Returns the project properties as a Python dictionary.\nReference: W-2024.09'
        return cls.call('get_project_properties', session=session)

    @classmethod
    def get_sfu_properties(cls, sfu_uuid, *, session='default'):
        'Returns a dictionary containing all the SFU properties for the\ntop-level SFU having the given uuid. Some properties are read-only.\nIf a property is not defined, key will be mapped to None.\n\nNote: dictionary is not bound to the SFU.\nChanging the returned object has no effect on the SFU.\n\nNote: dictionary with SFU parameters is not bound to the SFU.\nChanging the returned dictionary has no effect on the SFU.\nA new dictionary must be set for SFU parameters.\n\nList of editable properties: path, comment, enabled, parameters\nList of read-only properties: transient, error_info\nReference: W-2024.09'
        return cls.call('get_sfu_properties', sfu_uuid, session=session)

    @classmethod
    def get_silver_properties(cls, *, session='default'):
        "Returns Silver's properties as a Python dictionary.\nReference: W-2024.09"
        return cls.call('get_silver_properties', session=session)

    @classmethod
    def get_tab_folder_properties(cls, tab_folder_uuid, *, session='default'):
        "Get tab folder's properties.\n\nArgs:\n    tab_folder_uuid (str): The folder from which  the  properties  are\n        extracted.\n\nReturns:\n    dict: Containing  all  the  properties of the  tab  folder  having\n        the given uuid.\n\nNote:\n    Dictionary is not bound to the  tab  folder. Changing the returned\n    object has no effect on the tab folder.\n\nAvailable properties: 'width', 'active-tab'\n\nRaises:\n    ValueError: If tab_folder_uuid does not exist.\nReference: W-2024.09"
        return cls.call('get_tab_folder_properties', tab_folder_uuid, session=session)

    @classmethod
    def get_tab_folder_uuids(cls, *, session='default'):
        'Returns:\n    array: Containing the uuids  of  all  tab  folders  of the current\n     configuration.\nReference: W-2024.09'
        return cls.call('get_tab_folder_uuids', session=session)

    @classmethod
    def get_tab_properties(cls, tab_uuid, *, session='default'):
        "Get tab's properties.\n\nArgs:\n    tab_uuid (str): The tab from which the properties are extracted.\n\nReturns:\n    dict: Containing all the properties of the tab  having  the  given\n        uuid.\n\nNote:\n    Dictionary is not bound to the tab. Changing the  returned  object\n        has no effect on the tab.\n\nAvailable properties: 'name'.\n\nRaises:\n    ValueError: If tab_uuid does not exist.\nReference: W-2024.09"
        return cls.call('get_tab_properties', tab_uuid, session=session)

    @classmethod
    def get_tab_uuids(cls, folder_uuid, *, session='default'):
        'Returns:\n    array: Containing the uuids of all tabs under a given folder_uuid.\n\nArgs:\n    folder_uuid (str): the parent folder id of the returned tabs.\n\nRaises:\n    ValueError: If folder_uuid does not exist.\nReference: W-2024.09'
        return cls.call('get_tab_uuids', folder_uuid, session=session)

    @classmethod
    def get_top_level_module_and_sfu_uuids(cls, *, session='default'):
        'Returns a list of all top level modules and SFUs.\nList includes uuids for disabled modules and SFUs.\nList does not include uuids for SFUs that are part of another SFU.\nReference: W-2024.09'
        return cls.call('get_top_level_module_and_sfu_uuids', session=session)

    @classmethod
    def get_top_level_module_uuids(cls, *, session='default'):
        'Returns a list of all top level module uuids.\nList includes uuids for disabled modules.\nList does not include uuids for modules that are part of an SFU.\nReference: W-2024.09'
        return cls.call('get_top_level_module_uuids', session=session)

    @classmethod
    def get_top_level_sfu_uuids(cls, *, session='default'):
        'Returns a list of all top level SFU uuids.\nList includes uuids for disabled SFUs.\nList does not include uuids for SFUs that are part of an SFU.\nReference: W-2024.09'
        return cls.call('get_top_level_sfu_uuids', session=session)

    @classmethod
    def get_variable_string_value(cls, variable_name, *, session='default'):
        'Reads the variable value as String. Returns None if variable value\nis not a valid String handle or no module writes this variable.\nReference: W-2024.09'
        return cls.call('get_variable_string_value', variable_name, session=session)

    @classmethod
    def get_widget_properties(cls, widget_uuid, *, session='default'):
        "Get widget's properties.\n\nArgs:\n    widget_uuid (str):  The  widget  from  which  the  properties  are\n        extracted.\n\nReturns:\n    dict: Containing all the properties of the widget having the given\n        uuid.\n\nNote:\n    Dictionary is not bound  to  the  widget.  Changing  the  returned\n    object has no effect on the widget.\n\nAvailable editable properties: 'name', 'description', 'internal-bounds',\n    'external-bounds'.\nAvailable   read-only    properties:     'class',     'input-variables',\n    'output-variables', 'modified-variables'.\n\nRaises:\n    ValueError: If widget_uuid does not exist.\nReference: W-2024.09"
        return cls.call('get_widget_properties', widget_uuid, session=session)

    @classmethod
    def get_widget_uuids(cls, tab_uuid, *, session='default'):
        'Returns:\n    array: Containing the uuids of all widgets under a given tab_uuid.\n\nArgs:\n    tab_uuid (str): the parent tab id of the returned widgets.\n\nRaises:\n    ValueError: If tab_uuid does not exist.\nReference: W-2024.09'
        return cls.call('get_widget_uuids', tab_uuid, session=session)

    @classmethod
    def import_tab(cls, sil_file, tab_uuid, tab_folder_uuid, index=None, *, session='default'):
        "Imports a tab from a source sil into the current Silver configuration.\nThe import also includes all of the  tab's  hierarchy,  including  the\nchild widgets.\n\nArgs:\n    sil_file (str): The path of the source sil.\n    tab_uuid (str): The  tab  id  from  the source sil that need to be\n        imported.\n    tab_folder_uuid (str): The  parent  tab  folder id under which the\n        tab is added.\n    index (:obj:`int`, optional): the position of the  tab in the tabs\n        list. Affects the tab list order.  Default  value  is None. If\n        index is None  then  the  tab is added at the end of the list.\n\nReturns:\n    str: The  imported tab  id  which is different than the source tab\n        (the one from the source sil configuration).\n\nRaises:\n    ValueError: If tab_uuid does not exist in source sil.\n    ValueError: If  tab_folder_uuid  does  not  exist  in  the current\n        Silver configuration.\n    IndexError: If index not between [0, tab list size].\n    IOError: If .sil file does not exist or is inaccessible.\nReference: W-2024.09"
        return cls.call('import_tab', sil_file, tab_uuid, tab_folder_uuid, index, session=session)

    @classmethod
    def import_tab_folder(cls, sil_file, tab_folder_uuid, index=None, *, session='default'):
        "Imports a tab folder  from  a  source  sil  into  the  current  Silver\nconfiguration. The import also includes all of the  folder's hierarchy\n(tabs and tabs' widgets).\n\nArgs:\n    sil_file (str): The path of the source sil.\n    tab_folder_uuid (str): The tab folder id that  need to be imported\n        from the source sil to the current configuration.\n    index(:obj=`int`, optional):  The  position  of the tab  folder in\n        the tab folder list. Affects the tab folder order.  Default is\n        None.  If  index  is  None  the tab is added at the end of the\n        list.\n\nReturns:\n    str: The imported tab folder id which is different from the source\n        folder id (the one from the source sil).\n\nRaises:\n    ValueError: If tab_folder_uuid does not exist in source sil.\n    IndexError: If index not between [0, tab list size].\n    IOError: If .sil file does not exist or is inaccessible.\nReference: W-2024.09"
        return cls.call('import_tab_folder', sil_file, tab_folder_uuid, index, session=session)

    @classmethod
    def import_widget(cls, sil_file, widget_uuid, tab_uuid, *, session='default'):
        'Imports  a  widget   from  a  source  sil   into  the  current  Silver\nconfiguration.\n\nArgs:\n    sil_file (str): The path of the source sil.\n    widget_uuid (str): The widget id from the source sil that  need to\n    be imported.\n    tab_uuid (str): The parent tab id under which the widget is added.\n\nReturns:\n    str: The imported widget id  which  is  different  than the source\n    widget (the one from the sil configuration).\n\nRaises:\n    ValueError: If widget_uuid does not exist in source sil.\n    ValueError: If tab_uuid does  not  exist  in  the  current  Silver\n    configuration.\n    IOError: If .sil file does not exist or is inaccessible.\nReference: W-2024.09'
        return cls.call('import_widget', sil_file, widget_uuid, tab_uuid, session=session)

    @classmethod
    def log(cls, message, level='info', source=None, *, session='default'):
        'Logs messages to the Silver\'s console\n\nThis method is also available with the "runner" backend.\n\nArgs:\n    message: the message to be displayed in the console\n    level: (default is set to \'info\') available levels:\n        \'debug\', \'info\', \'warning\', \'error\' and \'fatal\'\n    source: (default is None) the caller information\n        (module/script , function name)\nReference: W-2024.09'
        return cls.call('log', message, level, source, session=session)

    @classmethod
    def open(cls, file_name, *, session='default'):
        'Opens the specified sil file. This method returns after the sil is\nloaded and all modules are loaded and\ninitialized. After this method returns, all variables are available.\n\nThis method is also available with the "runner" backend.\nReference: W-2024.09'
        return cls.call('open', file_name, session=session)

    @classmethod
    def pause(cls, *, session='default'):
        'Pauses the simulation after it has been started by calling the run()\nfunction. When this method ends, the simulation is paused.\nReference: W-2024.09'
        return cls.call('pause', session=session)

    @classmethod
    def pause_recording_variables(cls, file_name, *, session='default'):
        'Pauses writing to the specified file. File time is paused,\nso after resuming, the next data record will\nimmediately follow in the file the last record written before pausing.\nReference: W-2024.09'
        return cls.call('pause_recording_variables', file_name, session=session)

    @classmethod
    def playback_variables(cls, file_name, variable_names, *, session='default'):
        'Drives the variables with values from the specified file.\n\nNote: silver projects usually specify working directories,\nand Silver changes the current working directory when\nopening a project. If the file name is a relative path,\nit will be considered relative to that, and not the\ndirectory Silver is started from.\nReference: W-2024.09'
        return cls.call('playback_variables', file_name, variable_names, session=session)

    @classmethod
    def record_variables(cls, file_name, variable_names, use_simulation_start_time=False, *, session='default'):
        'Records the variables to the specified file.\n\nNote: silver projects usually specify working directories,\nand Silver changes the current working directory when\nopening a project. If the file name is a relative path,\nit will be considered relative to that, and not the\ndirectory Silver is started from.\nReference: W-2024.09'
        return cls.call('record_variables', file_name, variable_names, use_simulation_start_time, session=session)

    @classmethod
    def reload(cls, *, session='default'):
        'Restarts the simulation and resets all variable values\nalready set to None.\n\nThis method is also available with the "runner" backend.\nReference: W-2024.09'
        return cls.call('reload', session=session)

    @classmethod
    def remove_assignment(cls, assignment, *, session='default'):
        'Removes an assignment that has previously been added with\na call to add_assignment().\nReference: W-2024.09'
        return cls.call('remove_assignment', assignment, session=session)

    @classmethod
    def remove_config_parameter(cls, name, *, session='default'):
        'Removes, if exists, the configuration parameter having the given name.\n\nAfter changing parameters, simulation has to be restarted.\nThis function does not restart Silver, so that\nseveral parameters can be changed with a single simulation restart.\nReference: W-2024.09'
        return cls.call('remove_config_parameter', name, session=session)

    @classmethod
    def remove_module(cls, module_uuid, *, session='default'):
        'Removes the module from the configuration.\nIf there is no module with this uuid, or the uuid belongs to the\nGUI module, ValueError is raised.\nReference: W-2024.09'
        return cls.call('remove_module', module_uuid, session=session)

    @classmethod
    def remove_sfu(cls, sfu_uuid, *, session='default'):
        'Removes the SFU from the configuration.\nIf there is no top-level SFU with this uuid, or the uuid belongs to the\nGUI module, ValueError is raised.\nReference: W-2024.09'
        return cls.call('remove_sfu', sfu_uuid, session=session)

    @classmethod
    def remove_tab(cls, tab_uuid, *, session='default'):
        "Removes    the    specified    tab    from    the    current    Silver\nconfiguration.\n\nArgs:\n    tab_uuid (str): The tab to be removed.\n\nRaises:\n    ValueError: If the specified tab doesn't exist.\nReference: W-2024.09"
        return cls.call('remove_tab', tab_uuid, session=session)

    @classmethod
    def remove_tab_folder(cls, tab_folder_uuid, *, session='default'):
        "Removes   the   specified   tab   folder   from   the  current  Silver\nconfiguration.\n\nArgs:\n    tab_folder_uuid (str): The folder to be removed.\n\nRaises:\n    ValueError: If the specified tab folder doesn't exist.\nReference: W-2024.09"
        return cls.call('remove_tab_folder', tab_folder_uuid, session=session)

    @classmethod
    def remove_widget(cls, widget_uuid, *, session='default'):
        "Removes  the  specified  widget from the current Silver configuration.\n\nArgs:\n    widget_uuid (str): The widget to be removed.\n\nRaises:\n    ValueError: If the specified widget doesn't exist.\nReference: W-2024.09"
        return cls.call('remove_widget', widget_uuid, session=session)

    @classmethod
    def resume_playback_variables(cls, file_name, *, session='default'):
        'Continues playback of variables from the given file.\nThe file time depends on whether the writing process was\npaused or suppressed.\nReference: W-2024.09'
        return cls.call('resume_playback_variables', file_name, session=session)

    @classmethod
    def resume_recording_variables(cls, file_name, *, session='default'):
        'Continue writing to the specified file after writing has been suppressed.\nReference: W-2024.09'
        return cls.call('resume_recording_variables', file_name, session=session)

    @classmethod
    def run(cls, *, session='default'):
        'Asynchronously runs the simulation.\nThis function ends immediately, leaving Silver running.\n\nIf simulation is stopped (modules are not loaded) it will be started.\nReference: W-2024.09'
        return cls.call('run', session=session)

    @classmethod
    def run_for(cls, time, *, session='default'):
        'Runs synchronously the simulation for the specified amount of\nsimulation time in seconds and then pauses the simulation.\n\nIf simulation is stopped (modules are not loaded) it will be started.\n\nThis method is also available with the "runner" backend.\n\nRaises:\n    RuntimeError: if the simulation ended with error.\n    SystemError: if Silver crashed and reload should not be attempted.\nReference: W-2024.09'
        return cls.call('run_for', time, session=session)

    @classmethod
    def run_until(cls, condition_expression, timeout=0, *, session='default'):
        'Runs synchronously the simulation until either the expression evaluates\nto a non zero value, or the timeout expressed and measured in Silver\ntime expires, and then pauses the simulation and returns.\n\nIf simulation is stopped (modules are not loaded) it will be started.\n\nNote: timeout here is measured in Silver simulation time,\nunlike timeout for wait_until(), which is in actual wall-clock time.\n\nThis method is also available with the "runner" backend.\n\nArgs:\n    condition_expression: the expression that is evaluated each step.\n    timeout: the maximum allowed simulation time to wait until this\n        function returns, even if condition does\n        not hold. Specify 0 as timeout to wait forever.\nReturns:\n    True if the condition holds, and False if timeout expired\n    without the condition holding or silver was\n    stopped by a module.\nRaises:\n    RuntimeError if the simulation ended with error.\n    SystemError if Silver crashed and reload should not be attempted.\n    ValueError if condition expression is invalid\nReference: W-2024.09'
        return cls.call('run_until', condition_expression, timeout, session=session)

    @classmethod
    def save(cls, file_name, *, session='default'):
        'Saves the project to the specified file.\nReference: W-2024.09'
        return cls.call('save', file_name, session=session)

    @classmethod
    def set_config_parameter(cls, name, value, *, session='default'):
        'Sets a new configuration parameter or changes the value of an existing\nconfiguration parameter (in Silver Configuration tab).\n\nAfter changing parameters, simulation has to be restarted.\nThis function does not restart Silver, so that\nseveral parameters can be changed with a single simulation restart.\n\nThis method is also available with the "runner" backend.\nReference: W-2024.09'
        return cls.call('set_config_parameter', name, value, session=session)

    @classmethod
    def set_project_property(cls, name, value, *, session='default'):
        'Updates or resets to default a project property. If the value is null,\nthe value is reset to default. The list\nof properties available is given below:\n\nmacroStep\n    simulation step in seconds. Format: double.\n    Takes effect after simulation is restarted.\nspeedup\n    speedup factor. Format: double. Use 0 for maximum.\n    Example: 1 for real time, 0.5 for the simulation to run\n    twice as slow as real time.\nstartTime\n    initial time after a restart. Takes effect after the simulation is\n    restarted.\nguiDisabled\n    if set to True, all GUI outputs will be disabled\nparamsIniConfigPath\n    the path to the ini file describing the public parameters used\n    by the project.\nrealTime\n    if the Real Time Mode should be used (overrides speedup)\noptimizations\n    bit field of supported optimizations. Valid values include OR\n    combinations of the following:\n        1: unusedModuleIo - avoid copying of variables not read or\n        not written by modules\n        2: noDataHistory - disable storing history of variables\nReference: W-2024.09'
        return cls.call('set_project_property', name, value, session=session)

    @classmethod
    def set_variable_value(cls, variable_name, value, *, session='default'):
        'Sets a persistent value that will be set to this variable until this\nfunction is called again with value argument being null.\nAll values are reset to null when simulation is restarted.\n\nIn other words, you don\'t have to set this variable at each step.\n\nNote: all variable values will be removed when restart() is called.\n\nThis method is also available with the "runner" backend.\nReference: W-2024.09'
        return cls.call('set_variable_value', variable_name, value, session=session)

    @classmethod
    def set_module_position(cls, uuid, index, *, session='default'):
        'Moves module to the specified position.\nReference: W-2024.09'
        return cls.call('set_module_position', uuid, index, session=session)

    @classmethod
    def set_module_property(cls, module_uuid, name, value, *, session='default'):
        'Sets a property to the module identified by the given uuid.\nList of editable properties: sil_line, preview_sil_line, parallel,\nremote(deprecated | use remote_cluster), remote_cluster, enabled,\nprefix, suffix, input_rename_rules_file, output_rename_rules_file,\nmodify_rename_rules_file, multiply_macro_step, macro_step_multiplier\nList of read-only properties: display_name, error_info, is_gui, comment\nReference: W-2024.09'
        return cls.call('set_module_property', module_uuid, name, value, session=session)

    @classmethod
    def set_sfu_position(cls, sfu_uuid, index, *, session='default'):
        'Moves a top-level SFU to the specified position.\nReference: W-2024.09'
        return cls.call('set_sfu_position', sfu_uuid, index, session=session)

    @classmethod
    def set_sfu_property(cls, sfu_uuid, name, value, *, session='default'):
        'Sets a property to the top-level SFU identified by the given uuid.\nReference: W-2024.09'
        return cls.call('set_sfu_property', sfu_uuid, name, value, session=session)

    @classmethod
    def set_silver_property(cls, name, value, *, session='default'):
        'Updates or resets to default a silver property. If the value is null,\nthe value is reset to default. A silver property have a global effect,\ntherefore all Silver projects are affected. The list of available\nproperties is:\n\n    createBackupFiles\n        Create ".bak" backup files when overwriting .sil files\n    displayFullContextMenu\n        Allow shell extensions in context menus\n    scriptingApiLogDisabled\n        Disables scripting API logging\nReference: W-2024.09'
        return cls.call('set_silver_property', name, value, session=session)

    @classmethod
    def set_tab_folder_property(cls, tab_folder_uuid, name, value, *, session='default'):
        "Sets tab folder's property value.\n\nArgs:\n    tab_folder_uuid (str): Tab folder on which the property is set.\n    name (str): Property name.\n    value (type - depends  on  what  type  of  property is to be set).\n        Property value.\n\nAvailable property names:\n        'width' (str): sets  the  width  in  pixels of the tab folder.\n            value (int).\n        'active-tab' (str): sets the active tab (uuid - str) within\n            the tab folder.\nRaises:\n    ValueError: If tab_folder_uuid   does   not   exist.\n    KeyError: If property does  not  exist  (not  among  the  expected\n        property names).\n    TypeError: If property value is of incorrect  type  (eg. expecting\n        'int' received 'str').\nReference: W-2024.09"
        return cls.call('set_tab_folder_property', tab_folder_uuid, name, value, session=session)

    @classmethod
    def set_tab_property(cls, tab_uuid, name, value, *, session='default'):
        "Sets tab's property value.\n\nArgs:\n    tab_uuid (str): The tab on which the property is set.\n    name (str): Property name.\n    value (type - depends on  what  type  of  property  is to be set):\n        Property value.\n\nAvailable property names:\n    'name' (str):  Sets  string  containing the property {name} value.\n        value (str).\n\nRaises:\n    ValueError: If   tab_UUD   does   not   exist.\n    KeyError: If property does  not  exist  (not  among  the  expected\n        property names).\n    TypeError: If property value is of  incorrect  type (eg. expecting\n        'int' received 'str').\nReference: W-2024.09"
        return cls.call('set_tab_property', tab_uuid, name, value, session=session)

    @classmethod
    def set_widget_property(cls, widget_uuid, name, value, *, session='default'):
        'Sets widget\'s property value.\n\nArgs:\n    widget_uuid (str): The widget on which the property is set.\n    name (str): Property name.\n    value (type - a tuple of strings/or a string property  value(s) to\n        be set): Property value.\n\nAvailable property names:\n    \'name\' (str): Sets string containing the  property  {name}  value.\n        value (str).\n    \'description\' (str):  Sets  string   containing    the    property\n        {description} value. value (str).\n    \'internal-bounds\' (str): Sets a tuple of 4 containing the internal\n     bounds of the widget. order:[x, y, width, height]. value (tuple).\n    \'external-bounds\'  (str):  Similar   to  "internal-bounds".  value\n        (tuple).\n\nSpecial cases:\n    ValueError: If   widget_uuid   does   not   exist.\n    KeyError: If property does  not  exist  (not  among  the  expected\n        property names).\nReference: W-2024.09'
        return cls.call('set_widget_property', widget_uuid, name, value, session=session)

    @classmethod
    def started_successfully(cls, *, session='default'):
        'Returns True if Silver managed to load all modules successfully.\n\nThis method is also available with the "runner" backend.\nReference: W-2024.09'
        return cls.call('started_successfully', session=session)

    @classmethod
    def step(cls, *, session='default'):
        'Runs synchronously the simulation for one macro-step.\nEquivalent to run_for() if the argument is one macro step.\nReference: W-2024.09'
        return cls.call('step', session=session)

    @classmethod
    def stop(cls, *, session='default'):
        'Stops the simulation.\nReference: W-2024.09'
        return cls.call('stop', session=session)

    @classmethod
    def stop_playback_variables(cls, file_name, *, session='default'):
        'Stops the playback of variables for the given file name and the file is\nclose.\nReference: W-2024.09'
        return cls.call('stop_playback_variables', file_name, session=session)

    @classmethod
    def stop_writing_variables(cls, file_name, *, session='default'):
        'Stops recording the specified file. The file will be closed.\nReference: W-2024.09'
        return cls.call('stop_writing_variables', file_name, session=session)

    @classmethod
    def suppress_playback_variables(cls, file_name, *, session='default'):
        'Suppress playback of variables from the specified from the given file.\nOn resume, the time in the file will be\nincreased with the suppress duration,\nso some file data records will be lost/skipped. In analogy to a VCR/DVD\nplayer, this is equivalent to changing the channel on the TV,\nwhile the tape continues to roll.\nReference: W-2024.09'
        return cls.call('suppress_playback_variables', file_name, session=session)

    @classmethod
    def suppress_recording_variables(cls, file_name, *, session='default'):
        'Stops writing to the file, but the file time continues to increase,\nso after a resumeRecordingVariables(),\nthe file will have a gap in time between data written just prior\nto suppressing until recording is resumed.\nReference: W-2024.09'
        return cls.call('suppress_recording_variables', file_name, session=session)

    @classmethod
    def wait_until(cls, condition_expression, timeout=0, *, session='default'):
        'Waits until the condition is met or the timeout elapses.\nSilver must be running asynchronously from script when\nthis function is called.\n\nArgs:\n    condition_expression: the expression that is evaluated each step.\n    timeout: the maximum allowed simulation time to wait until this\n    function returns, even if condition does\n    not hold. Specify 0 as timeout to wait forever.\nReturns:\n    True if the condition holds, and False if timeout expired without\n    the condition holding or silver was\n    stopped by a module.\nReference: W-2024.09'
        return cls.call('wait_until', condition_expression, timeout, session=session)

