"""Helpers for writing, running, and repairing generated transformation code.

The generation scripts ask an LLM to produce Python code. This module is the
execution harness around that code: it writes generated code to disk, runs a
test function against it, and asks the LLM for fixes when the test crashes or
times out.
"""

import json
import os
import re
import shutil
import textwrap
import importlib
from concurrent.futures import ThreadPoolExecutor, TimeoutError

import tools.Code_Exec as Code_Exec
import tools.VisualQuestion as VQ


###############################################################################
def sanitize_code(code_str: str) -> str:
    """Clean up common Unicode punctuation in model-generated code."""
    for old, new in [('“','"'),('”','"'),('’','\''),('‘','\''),('—','-'),('–','-')]:
        code_str = code_str.replace(old, new)
    return code_str.strip()
###############################################################################################################################

def check_and_install_dependencies(code,model="",num_tries=3,messages=None):
    """Ask the model for dependency checks/install code and run that code.

    This is intentionally opt-in from ``run_debug_code`` because running
    installation code is consequential and can change the local environment.
    """
    if messages is None:
        prompt = ("Read the following code and see which packages/imports/dependencies does it use.\n"
                "Write  python script that check if all packages/imports/dependencies are available and install them if necessary\n"
                "\nThe answer most come in json format of {'packages': list of packages you need to install or 'None' if there arent any', 'installation_code': python code that check if the packages installed and install them if necessary (the code most be ready to run with no extra text). If no installations are needed leave empty.")
        messages = [
                     {"role": "system", "content": "You are a software developer ."},
                     {"role": "user", "content": prompt},
                     {"role": "user", "content": "Here is the code: \n\n"+code}

                   ]
    print(messages)



    for i in range(num_tries):
        results = VQ.get_reponse(messages = messages, model = model, as_json = True)
        messages.append({"role": "system", "content": str(results)})
        print(messages[-1])
        if i==0:
            installation_code = results.get('installation_code', '')
            if 'packages' not in results or results['packages'] == None or results['packages'] == [] or results['packages'] == "none" or len(
                installation_code) == 0: return True, messages, ""
            code_to_run = results['installation_code']
        else:
            if "yes" in str(results.get('solvable', '')).lower():
                code_to_run = results['fixed_code']
            else:
                return False, messages, ""


        print("Trying to install dependencies using:\n\n", textwrap.dedent(code_to_run))
        successed, captured_stdout, captured_stderr = Code_Exec.run_code(textwrap.dedent(code_to_run))
        if successed:   return True, messages, code_to_run

        messages.append({"role": "user", "content": "Failed installation with error:\n"+captured_stderr+" \n\n Try to solve the error. \n Give me your output as json file in the format:"
                       + " {'packages': list of packages you need to install or 'None' if there arent any\n,'solvable':can you solve the issue single word  answer: yes/no\n,'fixed_code':The fixed code ready to run}"})
        print(messages[-2:])
#--------------------------------------------------------------------------


    return False,messages, ""
##############################################################################################################33

def run_debug_code(messages, code, code_dir,codefilename,task_description,test_function,num_iter=4, clean_dir=True,time_out=0, rechek_code=False,model="", pre_install_dependency=False):
    """Write generated code to disk, run it, and ask the model to repair errors.

    Args:
        messages: Conversation history to use when asking the model for fixes.
        code: Generated Python source code.
        code_dir: Directory where the generated file and test outputs are saved.
        codefilename: Filename for the generated source, usually ``generate.py``.
        task_description: Natural-language task used for optional semantic checks.
        test_function: Callable that runs the generated code and raises on error.
        num_iter: Maximum repair attempts.
        clean_dir: Whether to delete ``code_dir`` before each attempt.
        time_out: Maximum seconds to wait for ``test_function``.
        rechek_code: When true, ask the model to inspect code after it runs.
        model: Model used for repair/check prompts.
        pre_install_dependency: Whether to let the model suggest install code.
    """

    # Install dependencies only when explicitly requested by the caller.
    code_verified = False # Does the code run smoothly
    if pre_install_dependency:
        inst_success, inst_logs, installation_code = check_and_install_dependencies(code, model=model)
        if not inst_success:
            return False, "", code_dir, code, "", inst_logs

    # Write, run, and optionally repair the generated file.
    for ii in range(num_iter):
        if os.path.exists(code_dir) and clean_dir: shutil.rmtree(code_dir)
        if not os.path.exists(code_dir): os.mkdir(code_dir)

        # Save code
        ###fname = f"{re.sub(r'[^a-zA-Z]', '_',method)}.py"
        path = os.path.join(code_dir, codefilename )

        with open(path, 'w', encoding='utf-8') as f: # save code
            f.write(code)#.replace("\\n", "\n)
        importlib.invalidate_caches() # import or reimport script


        # Run the generated code through the caller-provided test function.
        print("\n\n$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$\nRunning the code in " + path + "\n$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$4\n\n")

        out_text=""
        captured_err = ""

        is_error = False
        if time_out<=0: time_out= 5000


        try:
            with ThreadPoolExecutor() as executor:
                future = executor.submit(test_function, code_dir, code_dir + "//results")
                try:
                    result = future.result(timeout=time_out)
                    print("Result:", result)
                except TimeoutError:
                    # Function ran too long
                    captured_err += "\nThe code takes too long to run, try to make it more efficient.\n"
                    is_error = True
                    future.cancel()

        except Exception as err:
            # Catches crashes/exceptions thrown inside test_function
            is_error = True
            print("The program crashed")
            captured_err = "The code crashed with error:\n" + str(err)




        # If execution failed, ask the model for a fixed version and retry.
        if is_error:
            print("\niiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiii\n\nCODE running failed\niiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiii\n\n")
            text=("The code:***\n"+code+"\n***\n\nerror:***\n"+captured_err+"\n***"
               + "\nAnalyze the code and fix it if possible. Your response should come as  a dictionary,  json style with the following fields:\n"
                 "  {'fixable': can the code be fixed 'yes' or 'no','code':Fixed clean code,'details':Describe what errors you find and what changes you made,'dependencies': 'yes'/'no' do you want to install new dependencies or reinstall old one")
            messages.append({"role": "user","content": text})
            print(messages[-1])
            results = VQ.get_reponse(messages=messages,model=model,as_json=True)

            messages.append({"role": "system", "content":str(results)})
            print(messages[-1])

            if str(results.get('fixable', '')).lower() == "yes":
                 code=sanitize_code(results['code'])
                 if str(results.get('dependencies', '')).lower() == "yes":
                     inst_success, inst_logs, installation_code = check_and_install_dependencies(code,model=model)
                     messages+=inst_logs
                 continue
            else:
                break
        else:
            print("\n\nVVVVVVVVVVVVVVVVVVVVVVVVVV\nCODE running Succeed\nVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV\n\n")
            if task_description=="" or rechek_code==False:
                code_verified = True
                break

            # Optional semantic recheck after the generated code runs.
            text = ("***Analyze the following code***:\n" + code +
                    "\n\n***The code run smoothly and output:***\n" + out_text +
                    "\n\n***The task description for the code (what the code trying to do) is ***\n\n" + task_description +
                    "\n\n***GO over the code, the task description and output and see if you can spot any errors (ONLY ERRORS IN THE FEATURE EXTRACTURE CODE).\n Your  response should come as   json style with the following fields:  {'error':did you find errors in the code? 'yes'/'no','fixable': can the code be fixed 'yes' or 'no','code': the fixed code ready to run (note this part will run as is), 'description': Description of the error you found}***")
            messages.append({"role": "user","content": text})
            print(messages[-1])
         #   results = MainFunctions.get_reponse_as_json(text=text)# messages=messages

            results=VQ.get_response_image_txt_json(text=text, model=model)
            messages.append({"role": "system", "content": str(results)})
            print(messages[-1])

            if results.get("error") == "no":
                code_verified = True
                break
            else:
                if str(results.get('fixable', '')).lower() == "yes":
                    try:
                          code = sanitize_code(results['code'])
                    except KeyError as error:
                        print("Model said the code was fixable but did not return fixed code:", error)
                        break
                else:
                    break
    with open(os.path.join(code_dir, "Testing_logs.json"),"w", encoding="utf-8") as fl:
        json.dump(messages, fl, indent=4)

    with open(os.path.join(code_dir, "finish.txt"),"w",encoding="utf-8") as fl:
        fl.write("Finished")
    if code_verified:
        with open(os.path.join(code_dir, "verified.txt"), "w", encoding="utf-8") as fl:
            fl.write("Verified")



    return code_verified, path,code_dir, code, out_text,messages

#################################################################################################################33

def path_to_import(path: str, base: str = None) -> str:
    """Convert a filesystem path to a dotted Python import path.

    Non-identifier characters are replaced with underscores. If ``base`` is
    supplied, that prefix is stripped before the dotted module path is built.
    """
    # Normalize the path (removes duplicate slashes, handles .. and .)
    module_path = os.path.normpath(path)

    # Remove extension
    module_path = os.path.splitext(module_path)[0]

    # Strip base if given
    if base and module_path.startswith(base):
        module_path = module_path[len(base):]

    # Split into parts
    parts = module_path.strip(os.sep).split(os.sep)

    # Clean each part so it’s a valid Python identifier
    parts = [re.sub(r'[^0-9a-zA-Z_]', '_', p) for p in parts if p]
    txt_imp =  f" {'.'.join(parts)}"
    while txt_imp:
        if txt_imp[0] == "_" or txt_imp[0] == "." or txt_imp[0] == " ":
            txt_imp = txt_imp[1:]
        else:
            break
    return txt_imp
