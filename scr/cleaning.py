import os
import re
import json
from sklearn.preprocessing import MultiLabelBinarizer 
import itertools
import pandas as pd
import numpy as np
import webbrowser
from datetime import date


#--- basic cleaning ---#
def empty_list_to_string(x):
    if (isinstance(x,list) and len(x)==0):
        return ""
    else:
        return x
    
def remove_unit_signs(x):
    return re.sub("\s*m²|\s*€","",x)

def remove_thousand_dot(x):
    return re.sub("\.(?=[0-9]{3})","",x)

def replace_commas(x):
    return re.sub(",(?=[0-9]{1,2})",".",x)

def remove_rows_without_price_or_zip(df):
    tmpDf = df[["preis","plz"]]
    nrowComplete = df.shape[0]
    mask = tmpDf.preis.notna() & (df.plz!="")
    nrowClean = mask.sum()
    df = df.loc[mask]
    print(nrowComplete-nrowClean," rows without price and zip data were deleted")
    return df

def clean_df(df):
    df = df.applymap(empty_list_to_string)
    unitSignsList = ["preis", "wohnflaeche","grundstuecksflaeche"]
    df[unitSignsList] = (df[unitSignsList]
                         .applymap(remove_unit_signs)
                         .applymap(remove_thousand_dot)
                         )
    return df

#--- clean zip and place ---#
def get_zip_and_place(df):
    def funk(x):
        try:
            x = re.findall("\d{5}",x)[0] 
        except:
            x = ""
        return x
    df["plz"] = df.ort.apply(funk)

    df["ortsname"] = df.ort.apply(lambda x: re.sub("\d{5}","",x) if len(x)>0 else x)

    df = df.drop(["ort"],axis=1) 
    return df

#--- get binarized columns of characteristics ---#
def clean_merkmale(ser):
    ser = ser.apply(lambda x: re.sub('^, ','',x) if x is not None else x)#comma at the start
    ser = ser.apply(lambda x: re.sub(',$','',x) if x is not None else x)# comma at the end

    ser = ser.apply(lambda x: x.split(',') if x is not None else x) 
    ser = ser.apply(lambda x: [re.sub('^\s','',a) for a in x] if x is not None else x)#eliminate whitespace
    ser = ser.apply(lambda x: ["Keine Angabe"] if len(x)==1 else x)#set value for empty list
    print("merkmale cleaned and put into list")
    return ser

def binarize_merkmale(df):
    mlb = MultiLabelBinarizer()
    df["merkmale"] = clean_merkmale(df["merkmale"])
    dfMerkmale = pd.DataFrame(mlb.fit_transform(df.merkmale)
                             ,columns=mlb.classes_
                             ,index=df.index)
    df = pd.concat([df,dfMerkmale],axis=1)
    df = df.drop(['merkmale'],axis=1)
    print("merkmale binarized")
    return df

def set_key_value_as_index(df):
    df["id"] = df.url.apply(lambda x: re.findall(r"\w+",x)[-1])
    df = df.set_index("id",drop=True)
    return df

def drop_unprepared(df):
    """
    drops columns containing secondary information that have not yet been prepared
    """
    df = df.drop(["title","url","weitere_eigenschaften","beschreibung"],axis=1)
    return df



def prepare_price(df):
    """
    replaces commas with dots, replaces "auf Anfrage" (=on request) with empty string, 
    strips leading or trailing blanks and converts to float64
    
    """
    if df.preis.dtypes != "float64":
        tmp_preis = df.preis
        tmp_preis = tmp_preis.str.replace('auf Anfrage\xa0','')
        tmp_preis = tmp_preis.str.strip()
        tmp_preis = tmp_preis.apply(replace_commas)
        df["preis"] = pd.to_numeric(tmp_preis)
        print("preis has been cleaned up and converted to float")
    else: 
        print("preis is already float")
    return df

def clean_numerical_cols(df):
    numCols = ["anzahl_raeume","wohnflaeche","grundstuecksflaeche"]
    df[numCols] = df[numCols].applymap(replace_commas).applymap(pd.to_numeric)
    print("numerical columns:",', '.join(numCols),"cleaned")
    return df

def unpack_list_elements(df):
    """
    some columns' elements are lists. This is incompatible with eg drop_duplicates().
    This file unpacks them as str
    """
    listCols = ["weitere_eigenschaften","beschreibung"]
    df[listCols] = df[listCols].applymap(lambda x:", ".join(x))
    return df

# --- loading --- #

def extract_metadata_from_filename(jsonFileName):
    tmpDictCols = {}
    tmp = jsonFileName.split("-")
    tmpDictCols["transaktionsArt"] = tmp[-1].split(".")[0]
    tmpDictCols["objektArt"] = tmp[-2]
    tmpDictCols["datumDownload"] = "-".join(tmp[:3])
    tmpDictCols["suchOrt"] = "-".join(tmp[3:-2])
    return tmpDictCols

def insert_meta_data_columns(dfTmp,jsonFileName):
    """
    The json files do not contain metadata. They are read from the filename,
    prepared by extract_meta_data_from_filename and put into columns at the 
    start of the dataframe
    
    input:
        - df 
        - jsonFileName (str)
        
    output:
        - df
    """
    tmpDictCols = extract_metadata_from_filename(jsonFileName)
    for colNum, name in enumerate(tmpDictCols.keys()):
        dfTmp.insert(loc=colNum, column=name, value = tmpDictCols[name])
    return dfTmp

def get_pathdata_and_listfilenames(location="notebook"):
    """
    creates path to raw data in json format, and creates a generator with
    [path]/[filename]
    
    Paramaters:
        location (str): "notebook" if this file is run from notebook folder, 
                        if any other string if run from main folder of project.
    
    Returns:
        pathFile (generator)
    """
    pathData = os.path.join(".","data")
    if location =="notebook":
        pathData = os.path.join("..","data")
    jsonFilesList = [a for a in os.listdir(pathData) if re.findall("json$",a)]
    for fileName in jsonFilesList:
        pathFile = os.path.abspath(os.path.join(pathData,fileName))
        yield pathFile, fileName



def load_data(location="notebook"):
    """
    loads the data in data folder as json into pandas and adds metadata columns 
    derived from filenames
    
        Parameters:
            location (str): "notebook" if this file is run from notebook folder, 
                            if any other string if run from main folder of project.
            
        Results:
            df
    """
    
    dfList = []
    for pathFile, nameFile in get_pathdata_and_listfilenames():
        #print(nameFile)
        with open(pathFile) as data_file:    
            data = json.load(data_file)
        dfTmp = pd.json_normalize(data,['objects'])
        dfTmp = insert_meta_data_columns(dfTmp,nameFile)
        dfList.append(dfTmp)
    print(len(dfList),f' json-files have been loaded')
    df = pd.concat(dfList)
   
    return df

def load_and_prepare_data():
    df = load_data(location=None)
    df = set_key_value_as_index(df)

    df = clean_df(df)
    df = get_zip_and_place(df)
    df = remove_rows_without_price_or_zip(df)

    df = binarize_merkmale(df)
    df = unpack_list_elements(df)
    df = prepare_price(df)
    df["datumDownload"] = pd.to_datetime(df.datumDownload)    
    df = clean_numerical_cols(df)
    df = df.drop_duplicates()
    
    return df
def save_data_as_excel(df,location=None):
    today = pd.to_datetime('today')
    date = str(today.date())
    pathData = os.path.join(".","data",date)
    if location =="notebook":
        pathData = os.path.join("..","data",date)
    
    df[df.datumDownload==pd.to_datetime('today').normalize()].to_excel(date)