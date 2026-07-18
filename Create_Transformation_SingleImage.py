"""Create a reusable library of single-image transformations
Each transformation gradually transform image, PBR or any other map according to some rule, process, or model.

This script orchestrates an LLM-assisted transformation-library workflow:

1. Load prompt templates for a single-image transformation topics (image processing, math, biology, physics, art, tech...).
2. Ask an idea model to suggest new image transformation concepts.
3. Convert those suggestions into structured dataset entries.
4. Ask a coding model to implement each transformation as a Python generator.
5. Run the generated code, optionally ask a checker model for corrections, and
   persist all progress to ``data.pkl`` so interrupted runs can resume.

Each generated transformation is written into its own folder under the selected
library output directory.
"""

import os
import random

import tools.MainFunctions as MF
from datetime import datetime
import tools.VisualQuestion as VQ
import pickle
import json
import re
import run_single_im_transform as code_tester


DATASETS_KEY = "datasets"
LEGACY_DATASETS_KEY = "benchmarks"


# Suggest single-image transformation ideas, implement them as reusable code,
# and validate each generated implementation by running it on sample data.
def generate_transformation(dataset_dir, query_dir, number_of_new=10, number_of_code_fix_retry=2, recheck_originality=True, idea_model="", code_model="", check_model="", model="z-ai/glm-5.2"):
    """Generate and validate new single-image transformation dataset entries.

    Args:
        dataset_dir: Output directory for generated transformation folders and
            the persistent ``data.pkl`` state file.
        query_dir: Directory containing prompt templates used for idea
            generation, JSON conversion, code implementation, and code checks.
        number_of_new: Number of new transformation ideas to request from the
            idea model. Set to 0 to only continue existing entries.
        number_of_code_fix_retry: Number of checker/correction rounds to allow
            before accepting the current generated code result.
        recheck_originality: Reserved flag for a future originality pass. The
            current implementation keeps the value but does not use it.
        idea_model: Model used to suggest transformation ideas. Defaults to
            ``model``.
        code_model: Model used to write and debug generator code. Defaults to
            ``model``.
        check_model: Model used to inspect generated code for issues. Defaults
            to ``model``.
        model: Fallback model name used when a stage-specific model is omitted.

    Side effects:
        Creates output folders, writes generated code, and updates
        ``data.pkl`` / ``data_back.pkl`` with prompts, model responses, code,
        validation status, and dataset metadata.
    """
    if idea_model == "": idea_model = model # model used to suggest ideas
    if code_model == "": code_model = model # model used to implement and debug code
    if check_model == "": check_model = model  # model used to check generated code for errors

    # Persistent state files. The main pickle is updated throughout the run so a
    # later invocation can continue without regenerating already verified code.
    data_file = dataset_dir + "//data.pkl" # main state/log file for generated code and descriptions
    data_file_back = dataset_dir + "//data_back.pkl"


    if not os.path.exists(dataset_dir): os.mkdir(dataset_dir) # output dir

    # Load all prompt templates. Template filenames become keys under dt['qr'].
    # Some prompt filenames still use legacy wording, but in this script they
    # represent transformation-library generation steps.
    dt={'qr': {}, "messages":[]} # Queries and conversation history for the LVLMs
    for fl in os.listdir(query_dir):
        dt['qr'][fl] = open(query_dir + "//" + fl, "r", encoding="utf-8").read()

    # Resume from a previous run if a state file already exists. Prompt
    # templates are refreshed from disk, but generated transformation entries
    # are reused.
    data_file_loaded=False
    if os.path.isfile(data_file):
        print("\n\n\nLoad file\n\n\n")
        qr=dt['qr']
        dt=pickle.load(open(data_file,"rb"))
        dt['qr']=qr
        data_file_loaded=True

        # Older pickle files used the legacy key. Migrate it to the clearer
        # datasets key so the rest of this script uses dataset terminology.
        legacy_datasets = dt.pop(LEGACY_DATASETS_KEY, None)
        if DATASETS_KEY not in dt or dt[DATASETS_KEY] is None:
            dt[DATASETS_KEY] = legacy_datasets or {}
        elif legacy_datasets:
            for dataset_name, dataset_entry in legacy_datasets.items():
                dt[DATASETS_KEY].setdefault(dataset_name, dataset_entry)
        legacy_datasets_text = dt.pop("benchmarks_text", None)
        if "datasets_text" not in dt and legacy_datasets_text is not None:
            dt["datasets_text"] = legacy_datasets_text

        # Drop malformed or overlapping entries that do not have generated code
        # so old failed suggestions do not block future runs.
        to_remove=[]
        if DATASETS_KEY not in dt or dt[DATASETS_KEY] is None: dt[DATASETS_KEY] = {}
        for dataset_name in dt[DATASETS_KEY]:
            ent = dt[DATASETS_KEY][dataset_name]
            if 'full_overlap' in ent and ent['full_overlap'] == True and 'code' not in ent:
                to_remove.append(dataset_name)
            if not isinstance(ent , dict) or 'description' not in ent:
                to_remove.append(dataset_name)
        for dataset_name in to_remove:
                print("Removing:",dataset_name)
                del dt[DATASETS_KEY][dataset_name]

    # Suggest new transformation ideas and merge them into the persistent state.
    if  number_of_new>0:
        print("\n\n\nSuggest Model for Patterns and Texture generations\n\n\n")
        txt=dt['qr']['suggest_benchmarks'].replace("@@@number_of_new@@@",str(number_of_new))
        if data_file_loaded:
            # Include existing transformation names so the idea model is less
            # likely to repeat transformations that are already in the library.
            txt+=dt['qr']['add_suggestions']+ "\n Previous suggested methods: ["
            for ky in dt[DATASETS_KEY]:
                txt+=str(ky)+","
            txt+"]"

        resp,dt= VQ.get_reponse(dt, text=txt, model=idea_model) # suggest transformation ideas

        # Convert the free-form idea response into structured dataset entries
        # that can be iterated and resumed across script invocations.
        dt['datasets_text']=resp
        dt['messages'].append({"role": "user", "content":dt['qr']['suggestions_to_json']})
        dataset_dic,dt = VQ.get_reponse(dt, messages=dt['messages'][-3:],as_json=True, model=idea_model)
        if DATASETS_KEY in dt:
           for ky in dataset_dic:
                if ky not in dt[DATASETS_KEY]:
                    dt[DATASETS_KEY][ky]=dataset_dic[ky]
                    print(dataset_dic[ky])
                else:
                    print("error ", ky, "already exists")
        else:
           dt[DATASETS_KEY]=dataset_dic
        pickle.dump(dt, open(data_file, "wb"))


    # Generate code for each transformation that has not already been verified.
    if DATASETS_KEY not in dt:
           dt[DATASETS_KEY] = {}
    for dataset_name in dt[DATASETS_KEY]:
        print("transformation",dataset_name)
        ent=dt[DATASETS_KEY][dataset_name]

        dataset_description = ent["description"]


        # Skip entries that are already done or intentionally ignored.
        if ('code' in ent) and ('code verified' in ent['code'] or 'finished_and_failed' in ent['code']): continue
        if 'full_overlap' in ent: continue

        code_query=dt['qr']['implement_code'].replace("@@@Method Name@@@",dataset_name).replace("@@@Method Description@@@",dataset_description)
        if (not 'code' in ent) or ('Succeed' not in ent['code']):# or ent['code']['Succeed']=='no':
                    print("\n\n\nWrite code for:" + dataset_name + "\n\n\n")
                    for gg in range(10):
                        print(code_query)
                        code_dic, dt = VQ.get_reponse(dt, text=code_query, as_json=True, model=code_model)
                        if ('code' in code_dic) and  ('Succeed' not in code_dic) and len(code_dic['code'])>100: code_dic['Succeed']="yes"
                        if ('Succeed' not in code_dic):
                      #       code_query+="\n\nIts very important that the output will be in the precise format described aboce\n\n"
                             continue
                        dt[DATASETS_KEY][dataset_name]['code'] = code_dic
                        dt[DATASETS_KEY][dataset_name]['code']['query'] = code_query
                        break
                    pickle.dump(dt, open(data_file, "wb"))
                    pickle.dump(dt, open(data_file_back, "wb"))

        # Run, debug, and validate the generated code for the current transformation.

        if ent['code']['Succeed']=='no': continue

        if 'code verified' not in ent['code'] or ent['code']['code verified']==False:
            print("\n\n\nTest and validate  code for:" + dataset_name + "\n\n\n")
            sname = f"{re.sub(r'[^a-zA-Z]', '_', dataset_name)}"
            dt[DATASETS_KEY][dataset_name]['simple name']= sname
            outcodedir= dataset_dir + "//" + sname + "//"
            dt[DATASETS_KEY][dataset_name]['dir'] = outcodedir

            for kk in range(number_of_code_fix_retry+100):
                if not os.path.exists(dataset_dir): os.mkdir(outcodedir)
                code = dt[DATASETS_KEY][dataset_name]['code']['code']
                ln=len(dt['messages'])


                # Execute generated code through the shared debug harness. The
                # harness can patch obvious runtime issues before returning.
                code_verified, path, test_dir, code, captured_stdout, messages =  (MF.run_debug_code(messages =dt['messages'][-2:], code=code,  code_dir=outcodedir, codefilename="generate.py",
                                                                                                    task_description=dataset_description,
                                                                                                    time_out=140,
                                                                                                    rechek_code=False,
                                                                                                    model=code_model,
                                                                                                    test_function=code_tester.run_test))

                with open(test_dir+"//Description.txt","w") as fl: fl.write(dataset_description) # write transformation description
                with open(test_dir + "//models.txt", "w") as fl:
                    fl.write("Code model:"+code_model+"\n idea model"+idea_model)
                if  "overlap" in ent:
                    json.dump(ent["overlap"],open(test_dir+"//overlap.json","w"))

                # Ask a separate checker model to inspect the generated code and
                # task requirements. If it returns corrections, replace the
                # current code entry and loop again.
                find_error = False
                if not code_verified:
                    dt['messages']=dt['messages'][:ln]
                    break
                txt = "\n\n\n***Your task:***\n" + dt['qr']['check_code']
                txt +="***Original Code Generation task:***\n"+code_query+"\n\n\n"
                txt+="***Generated Code***:\n"+code+"\n\n\n"
                txt+="The code run on time and did not crash.\n"

                # Limit correction rounds. Extra attempts are only useful when
                # the checker identifies a concrete problem.
                if kk >= number_of_code_fix_retry and not find_error: break
                if kk >= number_of_code_fix_retry+3: break

                verify_query=txt
                print(txt)
                code_dic, dt = VQ.get_reponse(dt, text=verify_query, as_json=True, model=check_model) # Ask the checker LLM to identify and correct errors

                if 'corrections' in code_dic and code_dic['corrections']=='yes':# and len(code_dic['code'])>0:
                    print("\\n\n\n****************************************************************************\n\n\nCode correction found:",code_dic)
                    del dt[DATASETS_KEY][dataset_name]['code']
                    dt[DATASETS_KEY][dataset_name]['code'] = code_dic
                    dt[DATASETS_KEY][dataset_name]['code']['Succeed'] = 'yes'
                    dt[DATASETS_KEY][dataset_name]['code']['query'] = code_query
                    dt[DATASETS_KEY][dataset_name]['code']['fixing_query'] = verify_query

                else:
                    break


            # Finish one transformation entry and write both the primary state
            # file and a backup copy.
            dt[DATASETS_KEY][dataset_name]['code']['code verified'] = code_verified
            if not code_verified: dt[DATASETS_KEY][dataset_name]['code']['finished_and_failed']=True
            pickle.dump(dt,open(data_file,"wb"))
            pickle.dump(dt, open(data_file_back, "wb"))
            print("\n\n\n---------------------------------------------------\n\nFinished transformation ",dataset_name,"\nverified ",code_verified,"\n\n\nAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\n\n")

if __name__=="__main__":
        # Default batch runner. Each iteration chooses a prompt topic and model,
        # then appends several new single-image transformation ideas to that
        # topic's output directory. Existing data.pkl files make repeated runs
        # resumable.
        #--------------Input parameters
        models = ["z-ai/glm-5.2", "google/gemini-3.5-flash", "moonshotai/kimi-k2.6", "openai/gpt-5.5",
                  "openai/gpt-5.4"] # models used to suggest ideas broad range of models and choose randomly each time (use openrouter model)
        coding_models = ["z-ai/glm-5.2","moonshotai/kimi-k2.6","openai/gpt-5.4","google/gemini-3.5-flash"] # models used to implement ocdee
        main_query_dir= "queries_single_im"
        queries = os.listdir(main_query_dir) #["materials"]#
        main_out_dir = "out_single_imge_transformation/" # output dir where transformation will be saved
        if not os.path.exists(main_out_dir): os.makedirs(main_out_dir)

        print(queries)

        for ii in range(30):
            topic = random.choice(queries) # randomly pick topic of transformation (math, art, biology, image processing, camera effect...) basically pick set of queries correspond to the topic
            query_dir = os.path.join(main_query_dir,topic)  # Folder where prompts/queries are save
            outputdir = main_out_dir +"//"+topic +"//"  # output folder for the generated transformation dataset
            if not os.path.exists(outputdir): os.makedirs(outputdir)
            data_file = outputdir + "//data.pkl" # Data file containing all transformation-dataset state

            number_of_code_fix_retry = 0  # Number of checker correction rounds before accepting the result.
            recheck_originality=False #True # reserved for checking whether a transformation idea is already in the dataset
            #xiaomi/mimo-v2.5-pro #xiaomi/mimo-v2.5-pro"])#"google/gemini-3.1-pro-preview"])#"
            model = random.choice(coding_models)#penai/gpt-5.5"])#"google/gemini-3.1-flash-lite-preview","moonshotai/kimi-k2.6","xiaomi/mimo-v2.5-pro"])#,"openai/gpt-5.4","openai/gpt-5.5","google/gemini-3.1-pro-preview"])#"openai/gpt-5.5"])#"google/gemini-3.1-flash-lite-preview"#"openai/gpt-5.4"#google/gemini-3.1-flash-lite-preview"#"z-ai/glm-5.1"#"google/gemini-3.1-flash-lite-preview"#"z-ai/glm-5.1"#google/gemini-3.1-flash-lite-preview"#"z-ai/glm-5.1"## "google/gemini-3.1-flash-lite-preview"#"google/gemini-3-flash-preview" # model for writing code (and defult for everthing else) "z-ai/glm-4.7-flash"#"moonshotai/kimi-k2.6"#openai/gpt-5.2"#grok-4-fast-reasoning"#"Qwen/Qwen2.5-VL-72B-Instruct"#"claude-sonnet-4-5-20250929" #"grok-4-fast-reasoning"#"gemini-2.5-flash"#"Qwen/Qwen2.5-VL-72B-Instruct"#"gpt-5"
            idea_model =   random.choice(models)
            number_of_new= 4 # Number of new ideas to suggest in each round
            print(datetime.now())
            print("\n*************************\n"+idea_model,model,query_dir,"\n********************************\n")
            try:
                generate_transformation(dataset_dir=outputdir, query_dir=query_dir, number_of_new=number_of_new, number_of_code_fix_retry=number_of_code_fix_retry, recheck_originality=recheck_originality, model=model, idea_model = idea_model, check_model="google/gemini-3.5-flash")
            except Exception as e:
                print(e)

