#!/usr/bin/env python
"""
Python refactoring for TextMate via bicycle repair man. 

Requires Bicycle Repair Man from http://bicyclerepair.sourceforge.net/
"""

import sys, os, popen2, bike, logging
from urllib import pathname2url

brm = bike.init()

log_file = os.environ.get('BRM_TM_LOG','biketextmate.log')

logger = logging.getLogger()
handler = logging.FileHandler(log_file)
formatter = logging.Formatter('[%(asctime)s] %(funcName)s :: %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)



####################################
### Bicycle Repair Man functions ###
####################################


def findDefinition():
    """ Find the definition of the item under the cursor.
    """
    file_path, row, col = getLocationOfCaret()
    matches = list(brm.findDefinitionByCoordinates(file_path, row, col))
    if len(matches) == 1:
        definition = matches[0]
        setCaretLocation(definition.filename, definition.lineno, definition.colno)
    elif len(matches) > 1:
        messageBox("Multiple definitions for '%s' found." % getCurrentWord() )
    else:
        messageBox("No definitions for '%s' found." % getCurrentWord() )


def extractMethodOrFunction():
    """ Extract the selection into a separate function.  
    """
    file_path, start_row, start_col, end_row, end_col = getLocationOfSelection()
    new_name = inputBox('What would you like to call the extracted method/function?')
    if new_name: 
        brm.extractMethod(file_path, start_row, start_col, end_row, end_col, new_name)
        saveAndReload(file_path, start_row, start_col)
    

def rename():
    """ Rename the object under the caret. 
    """
    file_path, row, col = getLocationOfCaret()
    old_name = getCurrentWord()
    new_name = inputBox("What new name would you like for '%s'?" % old_name, old_name)
    
    if new_name and new_name != old_name:
        # if we don't use the definition location, only the definition is renamed.
        # either there's a bug in BRM or I'm calling it incorrectly
        matching_definitions = brm.findDefinitionByCoordinates(file_path, row, col)
        try:
            definition = matching_definitions.next()
            brm.renameByCoordinates(definition.filename, definition.lineno, definition.colno, new_name)
            saveAndReload(file_path, row, col)
        except StopIteration:
            messageBox("No definition for '%s' found." % old_name)


def inlineLocalVariable():
    """ Inline a local variable under the caret. 
    """
    file_path, row, col = getLocationOfCaret()
    brm.inlineLocalVariable(file_path, row, col)
    saveAndReload(file_path, row, col)


def extractLocalVariable():
    """ Extract a local variable from the current selection. 
    """
    file_path, start_row, start_col, end_row, end_col = getLocationOfSelection()
    var_name = inputBox("What name would you like for the local variable?")
    if var_name:
        brm.extractLocalVariable(file_path, start_row, start_col, end_row, end_col, var_name)
        saveAndReload(file_path, start_row, start_col)



############################
### TextMate interaction ###
############################


def getCurrentWord():
    """ The word under the caret. 
    """
    return getTMEnvironmentVariable('TM_CURRENT_WORD')


def getLocationOfCaret():
    """ The caret location as a filepath, line number (1 indexed), column index
        tuple. 
    """
    file_path = getTMEnvironmentVariable('TM_FILEPATH')
    row = int(getTMEnvironmentVariable('TM_LINE_NUMBER'))
    col = int(getTMEnvironmentVariable('TM_LINE_INDEX'))

    logger.debug("Caret at (%d,%d)"% (row, col))
    return file_path, row, col


def getLocationOfSelection():
    """ The current selection as a filepath, start line no (1 indexed), 
        start column no, end line no, end column no tuple. 
    """
    # There are no environment variables for the beginning and end of a
    # selection, so we need to do some detective work based on the selection
    # itself, the current line and the location of the caret. 

    try:
        selected_text = getTMEnvironmentVariable('TM_SELECTED_TEXT')
    except RuntimeError:
        raise RuntimeError("You need to select some text to do that.")

    current_line_text = getTMEnvironmentVariable('TM_CURRENT_LINE')
    file_path, caret_row, caret_col = getLocationOfCaret()
    
    selected_lines = selected_text.splitlines()
        
    # single line selection?
    if len(selected_lines) == 1:
        start_row = end_row = caret_row

        # The caret may be in the middle of the selection. 
        start_col = findSpanning(current_line_text, selected_text, caret_col)

        if start_col == -1:
            logger.warning("findSpanning call failed. current line = '%s' selected text = '%s' caret column = %d"
                % (current_line_text, selected_text, caret_col))
        end_col = start_col + len(selected_text)        
    
    # multiline selection with caret in first line?
    elif current_line_text.endswith(selected_lines[0]):
        start_row = caret_row
        start_col = current_line_text.rfind(selected_lines[0])
        end_row = start_row + len(selected_lines) - 1
        end_col = len(selected_lines[-1])
    
    # multiline selection with caret in last line?
    else:
        source_lines = open(file_path).readlines()
        last_line_index = None
        
        # (-1 because we're converting count from 1 to count from 0)
        if source_lines[caret_row-1].startswith(selected_lines[-1]):
            last_line_index = caret_row-1
        # if select to the end of the line, caret's actually located
        # at the beginning of the next line -> -2
        elif source_lines[caret_row-2].startswith(selected_lines[-1]):
            last_line_index = caret_row-2
        
        if last_line_index:
            end_row = last_line_index+1
            start_row = end_row - len(selected_lines) + 1
            end_col = len(selected_lines[-1])
            start_col = source_lines[start_row-1].find(selected_lines[0])

        else:
            raise  RuntimeError("A multiline selection should begin or end with a caret.")
            
    logger.debug("(%d,%d) - (%d,%d)" % (start_row, start_col, end_row, end_col) )
    return file_path, start_row, start_col, end_row, end_col


def findSpanning(string, substring, span_index):
    """ Return the index of the first occurence of
        substring in string that contains span_index.
        Or -1 if no such substring exists. 
    """
    substring_length = len(substring)

    start = max(span_index - substring_length, 0)
    inclusive_end = min(span_index, len(string) - substring_length)
    
    for i in range(start, inclusive_end + 1):
        logger.debug("'%s'=='%s'?" % (string[i:i + substring_length], substring))
        potential_match = string[i:i + substring_length]
        if potential_match == substring:
            logger.debug("match: '%s'=='%s'" % (potential_match, substring))
            return i
    return -1


def getTMEnvironmentVariable(var_name):
    """ Return the value of a TextMate defined environment variable. 
    """
    if var_name not in os.environ:
        raise  RuntimeError("%s environment variable not defined.\n"\
            "Perhaps the script is not being run as a bundle?" % var_name)
    return os.environ[var_name]


def setCaretLocation(filepath, line, column, defocus=False):
    """ Move the caret to the given location. 
        If defocus is True, uses a work-around to force TextMate
        to move the caret after reloading. 
    """
    if defocus:
        osascript(['tell application "Finder"', 'activate', 'end tell'])
    os.system('open "txmt://open?url=file://%s&line=%d&column=%d"' %\
        (pathname2url(filepath), line, column+1))


def reloadAllFiles():
    """ Reload all open files. 
        Call after Bicycle Repair Man has made changes. 
    """
    command = '. \"%s/lib/bash_init.sh\"; rescan_project' % getTMSupportFolderPath()
    os.system(command)


def saveAndReload(file_path, row, col):
    """ Save in Bicycle Repair Man, reload all files in TextMate, 
        then set the caret back to the (presumably) original location. 
    """
    brm.save()
    reloadAllFiles()
    setCaretLocation(file_path, row, col, defocus=True)


def osascript(lines):
    """Pass a sequence of lines to the system's `osascript` command.
    """
    bits = ['osascript'] + ["-e '%s'" % line for line in lines]
    os.system(' '.join(bits))
    
    
####################
### Cocoadialog ###
####################


common_cocoa_dialog_options = ' --title "Bicycle Repair Man" --float '

def inputBox(text, default=""):
    """ Return response from a CocoaDialog input box.
        (None if cancelled).
    """
    command = '"%s" inputbox %s --text "%s" --informative-text "%s"'\
              ' --button1 "Okay" --button2 "Cancel"'\
              % (getCocoaDialogPath(), common_cocoa_dialog_options, default, text)

    fromchild, tochild = popen2.popen2(command)
    button = fromchild.readline()
    output = fromchild.readline()

    if int(button) == 1: 
        return output.strip()
    else:
        return None


def yesNoBox(text):
    """ Return a boolean response from a CocoaDialog yes/no box. 
    """
    command = '"%s" yesno-msgbox %s --no-cancel --text "%s"'\
               % (getCocoaDialogPath(), common_cocoa_dialog_options, text)

    fromchild, tochild = popen2.popen2(command)
    button = fromchild.readline()

    return int(button) == 1


def messageBox(text, details=None):
    """ Display a CocoaDialog message box. 
    """
    command = '"%s" ok-msgbox --no-cancel %s --text "%s"'\
               % (getCocoaDialogPath(), common_cocoa_dialog_options, text)

    if details:
        command += ' --informative-text "%s"' % details

    os.system(command)


def getTMSupportFolderPath():
    """ Return the absolute path to the TextMate support folder. 
    """
    return getTMEnvironmentVariable('TM_SUPPORT_PATH')


def getCocoaDialogPath():
    """ Return the absolute path to CocoaDialog binary. 
    """
    return getTMSupportFolderPath() + "/bin/CocoaDialog.app/Contents/MacOS/CocoaDialog"


################
### __main__ ###
################

command_line_args = dict(
    rename = rename,
    finddefinition = findDefinition,
    extractmethodorfunction = extractMethodOrFunction,
    inlinelocalvariable = inlineLocalVariable,
    extractlocalvariable = extractLocalVariable,
    )
     
if __name__=="__main__": 
    
    if len(sys.argv) != 2:
        print "usage: python biketextmate.py [%s]" % "|".join(sorted(command_line_args.keys()))
        print "from within a TextMate bundle command."
        sys.exit()
    
    elif sys.argv[1] not in command_line_args:
        messageBox("'%s' is not a valid argument." % sys.argv[1],  details="See source for details.")
        sys.exit()

    try:
        command_line_args[sys.argv[1]]()

    except (SystemExit):
        pass

    except (RuntimeError), e:
        logger.exception("RuntimeError caught.")
        messageBox("Oops.", details=e.message)

    except (Exception), e:
        logger.exception("Exception caught.")
        messageBox("'%s' was raised. See log for details. " % type(e).__name__, details=e.message)
