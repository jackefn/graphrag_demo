import os

import pandas as pd
import tiktoken

from graphrag.query.context_builder.entity_extraction import EntityVectorStoreKey
from graphrag.query.indexer_adapters import (
    read_indexer_covariates,
    read_indexer_entities,
    read_indexer_relationships,
    read_indexer_reports,
    read_indexer_text_units,
)
from graphrag.query.input.loaders.dfs import (
    store_entity_semantic_embeddings,
)
from graphrag.query.llm.oai.chat_openai import ChatOpenAI
from graphrag.query.llm.oai.embedding import OpenAIEmbedding
from graphrag.query.llm.oai.typing import OpenaiApiType
from graphrag.query.question_gen.local_gen import LocalQuestionGen
from graphrag.query.structured_search.local_search.mixed_context import (
    LocalSearchMixedContext,
)
from graphrag_r.query.structured_search.local_search.search import LocalSearch
from graphrag.vector_stores.lancedb import LanceDBVectorStore
from graphrag_r.query.structured_search.fixed_local_index import FIXED_LOCAL_INDEX,CHUNK_PROMPT,JUDGE_DISEASE_PROMPT
import openai
from openai import OpenAI


# 调用deepseek模型
def get_deepseek_response(query=""):
    client = OpenAI(api_key="sk-ae927ed128bd4e7e8255be1cd5ab395e", base_url="https://api.deepseek.com")
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": query},
        ],
        stream=False
    )
    return response.choices[0].message.content


INPUT_DIR = "/home/xiangchao/home/muxinyu/graphrag_demo/ragtest/output/20240810-104628/artifacts"
LANCEDB_URI = f"{INPUT_DIR}/lancedb"

COMMUNITY_REPORT_TABLE = "create_final_community_reports"
ENTITY_TABLE = "create_final_nodes"
ENTITY_EMBEDDING_TABLE = "create_final_entities"
RELATIONSHIP_TABLE = "create_final_relationships"
TEXT_UNIT_TABLE = "create_final_text_units"
COMMUNITY_LEVEL = 2
entity_df = pd.read_parquet(f"{INPUT_DIR}/{ENTITY_TABLE}.parquet")
entity_embedding_df = pd.read_parquet(f"{INPUT_DIR}/{ENTITY_EMBEDDING_TABLE}.parquet")

entities = read_indexer_entities(entity_df, entity_embedding_df, COMMUNITY_LEVEL)

description_embedding_store = LanceDBVectorStore(
    collection_name="entity_description_embeddings",
)
description_embedding_store.connect(db_uri=LANCEDB_URI)
entity_description_embeddings = store_entity_semantic_embeddings(
    entities=entities, vectorstore=description_embedding_store
)

relationship_df = pd.read_parquet(f"{INPUT_DIR}/{RELATIONSHIP_TABLE}.parquet")
relationships = read_indexer_relationships(relationship_df)

report_df = pd.read_parquet(f"{INPUT_DIR}/{COMMUNITY_REPORT_TABLE}.parquet")
reports = read_indexer_reports(report_df, entity_df, COMMUNITY_LEVEL)


text_unit_df = pd.read_parquet(f"{INPUT_DIR}/{TEXT_UNIT_TABLE}.parquet")
text_units = read_indexer_text_units(text_unit_df)


api_key = "fk227782-dvgh0rCcp2ZhANj6B1dg18ACjGG82JLm"
llm_model = "gpt-4-turbo-preview"
embedding_model = "text-embedding-3-small"

llm = ChatOpenAI(
    api_key=api_key,
    api_base="https://openai.api2d.net/v1/",
    model=llm_model,
    api_type=OpenaiApiType.OpenAI,  
    max_retries=20,
)

token_encoder = tiktoken.get_encoding("cl100k_base")

text_embedder = OpenAIEmbedding(
    api_key=api_key,
    api_base="https://openai.api2d.net/v1/",
    api_type=OpenaiApiType.OpenAI,
    model=embedding_model,
    deployment_name=embedding_model,
    max_retries=20,
)
context_builder = LocalSearchMixedContext(
    community_reports=reports,
    text_units=text_units,
    entities=entities,
    relationships=relationships,
    entity_text_embeddings=description_embedding_store,
    embedding_vectorstore_key=EntityVectorStoreKey.ID,  
    text_embedder=text_embedder,
    token_encoder=token_encoder,
)
local_context_params = {
    "text_unit_prop": 0.6,
    "community_prop": 0,
    "conversation_history_max_turns": 5,
    "conversation_history_user_turns_only": True,
    "top_k_mapped_entities": 10,
    "top_k_relationships": 10,
    "include_entity_rank": True,
    "include_relationship_weight": True,
    "include_community_rank": False,
    "return_candidate_context": False,
    "embedding_vectorstore_key": EntityVectorStoreKey.ID,  
    "max_tokens": 12_000,  
}

llm_params = {
    "max_tokens": 2_000,  
    "temperature": 0.0,
}
search_engine = LocalSearch(
    llm=llm,
    context_builder=context_builder,
    token_encoder=token_encoder,
    llm_params=llm_params,
    context_builder_params=local_context_params,
    response_type="multiple paragraphs",  
)
question = """
    患者，马XX，男性，47岁，主因“日间思睡30年，猝倒发作13年”以“睡眠障碍”收入神内睡眠组。

现病史：患者于30年前因家中变故、情绪不佳出现日间思睡，表现为白天无法控制的睡意，多发生在上课时，睡眠数分钟后自行清醒，睡醒后有精力恢复感， 可继续听课，夜间睡眠无明显异常。28年前日间思睡加重，常有不分场合的入睡，如骑自行车时入睡导致摔倒；同时出现夜间入睡困难，上床1h后才可入睡，夜间睡眠浅，易醒，每晚可醒4-5次，再入睡困难，患者自述每晚睡眠时间仅有1-2h;患者有睡眠相关幻觉，具体为入睡时感觉到有人进入自己的房间；患者有睡眠瘫痪，表现为睡醒时全身一过性的不能活动，一周可出现2-3次；患者有打鼾，无睡眠中憋气惊醒，有记忆力下降。患者遂就诊于北京协和医院，诊断为“神经衰弱”，具体治疗不详。23年前患者行中药、针灸等治疗，夜间入睡困难、 夜间易醒症状有所改善，每晚可睡4-5h，日间思睡未见明显改善。3年前患者新冠病毒感染后夜间入睡困难、夜间易醒症状反复，每晚需2h左右可入睡，入睡后1-2h觉醒一次；日间思睡一天可有2次，每次睡眠半小时后有精力恢复感。去年患者就诊于北京协和医院，予“佐匹克隆”治疗，治疗初期入睡困难有所改善，治疗后期患者自觉无效，遂停药。患者于3个月前就诊于我院门诊，予“喹硫平” “乐友”“右佐匹克隆”“劳拉西泮”等治疗， 诉症状有所好转，白天可不困， 夜晚入睡困难减轻，觉醒频率降至每晚一次，夜间可睡4-5h。患者 13年前出现有积极情绪时全身发软，以面部为著，表现为说话费力、嘴抖等，数秒后自行缓解，无摔倒，意识清晰。患者为求进一步诊治，以“睡眠障碍”收入我科。患者自发病以来，精神可，食欲可，睡眠：晚10点上床，早7点起床，其余如上所述，有便秘，小便稍费力，体重去年一年增长5kg。

既往史：既往有鼻中隔偏曲手术史、 头部痣切除手术史。

个人生活史、家族史无特殊。

查体无明显阳性体征。

辅助检查：
2024-04-17，脑脊液常规 (样本：脑脊液):未见明显异常；
2024-04-17, 脑脊液生化 (样本：脑脊液):未见明显异常；
2024-04-18，免疫球蛋白(IgGIgMIgA)(样本： 脑脊液):脑脊液免疫球蛋白
A0.67mg/dl↑；
2024-04-18，免疫球蛋白(IgGIgMIgA)(样本：血清): 未见明显异常；
2024-04-18，血沉(样本：全血):未见明显异常；
2024-04-18，乙肝五项+丙型肝炎病毒抗体+HIVP24 抗原/抗体+梅毒螺旋体特异性抗体(样本：血清):未见明显异常；
2024-04-18，甲功全项(样本：血清): 未见明显异常；
2024-04-18，铁蛋白+叶酸+维生素B12+性激素六项(样本：血清):黄体生成激素1.03mIU/ml↓，催乳素14.99ng/ml↑，睾酮126.73ng/dL↓；
2024-04-18，血常规(样本：全血): ★红细胞计数5.62X1012/L↑；
2024-04-18，肿瘤全项(男)(样本：血清): 未见明显异常；
2024-04-18，尿常规(样本：尿液); 未见明显异常；
2024-04-18，便常规+潜血实验(样本： 粪便):未见明显异常；
2024-04-17，自身免疫性脑炎抗体谱检测1 (样本：脑脊液):未见明显异常；
2024-04-17，自身免疫性脑炎抗体谱检测1 (样本：血清):未见明显异常；
2024-04-17，神经副肿瘤综合征抗体谱检测 (样本：全血):未见明显异常；
2024-04-17，神经副肿瘤综合征抗体谱检测 (样本：脑脊液):未见明显异常；
2024-04-18，糖化血红蛋白(HPLC法)(样本： 全血):未见明显异常；
2024-04-18，转铁蛋白+转铁蛋白饱和度+同型半胱氨酸+血清铁+生化全项 (样本：血清):★高密度脂蛋白0.94mmol/L↓，血清铁181.00ug/d1↑，转铁蛋白1.48g/L↓，不饱和铁结合力18.50μmol/L↓；
2024-04-18，D-二聚体+凝血四项(样本： 血浆):未见明显异常；
2024-04-18，免疫五项+风湿三项(样本： 血清):抗链﹠quot;0&quot;抗体
247.00IU/ml↑；
脑脊液食欲素(金域):32.14pg/ml↓
多导睡眠监测：睡眠效率降低，睡眠潜伏期正常，睡眠中觉醒时间增多，睡眠中觉醒次数增多；睡眠结构紊乱，N1期比例增高，N2期比例减低，N3期比例减低，R期比例减低，R期潜伏期延长；睡眠监测中可见1次异常行为发作，表现为肢体剧烈抖动，持续时间约0.5s，发作前脑电为II期睡眠脑电，发作后清醒；睡眠监测中未见睡眠呼吸暂停低通气事件； 睡眠监测中符合轻度周期性腿动事件， PLM指数为11.4次/小时；R期可见阵发性肌电活动增高；请结合临床。
多次小睡试验：五次小睡试验中可见4次REM期起始睡眠，平均睡眠潜伏期为9.8分钟。

根据上述病例信息判断患者所患有的疾病
"""


result = search_engine.search(question)
print(result.response)
# 假设 result.context_data["sources"] 是一个 DataFrame
df = result.context_data["sources"]
num_rows = df.shape[0]  # 获取行数
if num_rows == 1:
    # print(111)
    full_text = ''.join(df['text'].apply(str))  # 获取text列内容
    chunk_query = CHUNK_PROMPT.format(full_text)
    chunk_result = get_deepseek_response(query=chunk_query)
    segements = chunk_result.split("**")[1:] # 分段
    output_str = ""
    for i, segment in enumerate(segements):
        # print(f"Segment {i+1}:\n{segment}\n")
        judge_result = get_deepseek_response(query=JUDGE_DISEASE_PROMPT.format(segment,result.response))
        # print(judge_result)
        if(judge_result == "是"):
            output_str += segment
    print(output_str)

else:
    output_str = ""
    for index, row in df.iterrows():
        full_text = row['text']
        chunk_result = get_deepseek_response(query=CHUNK_PROMPT.format(full_text))
        segements = chunk_result.split("**")[1:]
        for i, segment in enumerate(segements):
            judge_result = get_deepseek_response(query=JUDGE_DISEASE_PROMPT.format(segment,result.response))
            if(judge_result == "是"):
                output_str += segment
    print(output_str)