"""Pure/fake-adapter examples for documentation; no inference, network or hardware."""
from pathlib import Path
from copy import deepcopy
import json
from document_parser.math.latex_ast import parse_latex_to_ast
from document_parser.accessibility.flattening.structure_nodes import classify_ast_status, flatten_page
from document_parser.accessibility.speech.math_rules import math_focus_item_to_speech
from document_parser.accessibility.braille.math_translator import math_focus_item_to_braille
from document_parser.accessibility.braille.viewport import cell_to_int, build_frame, scroll
from document_parser.server.s1_parser import PaddleVlFragmentParser
from book_scanner.video.opaque_identity import OpaqueFooterTokenPair, OpaqueReferenceBank, OpaqueQueryCollector
from book_scanner.video.config import OpaqueFooterIdentityPolicy
from book_scanner.video.types import ArtifactId, FrameId

math=[]
for raw in [r'(x+1)^2=9', r'(x+\unsupported)^2=9', r'(x+1)^2=']:
    parsed=parse_latex_to_ast(raw)
    status=classify_ast_status(parsed.unconsumed_tokens,parsed.issues)
    item={'ast_status':status,'presentation_ast':parsed.ast}
    math.append({'input':raw,'ast':parsed.ast,'status':status,
                 'issues':parsed.issues,'unconsumed_tokens':parsed.unconsumed_tokens,
                 'speech':math_focus_item_to_speech(item),
                 'braille':[cell_to_int(c) for c in math_focus_item_to_braille(item)]})

def block(label,content,order):
    return {'block_label':label,'block_content':content,'block_order':order,
            'block_id':order,'block_bbox':[50,50+50*order,700,90+50*order]}
blocks=[block('display_formula',r'(x+1)^2=9',3),
        block('text','① 1 ② 2 ③ 3 ④ 4 ⑤ 5',4),
        block('text','[26008-0011]',1),
        block('text','다음 방정식의 양의 해를 고르시오.',2)]
class FakeVl:
    engine_id='documentation-fake-vl'
    engine_version='1'
    def __init__(self, data=blocks):self.data=data
    def parse_page(self,path):return {'width':1000,'height':1400,'parsing_res_list':deepcopy(self.data)}
parsed=PaddleVlFragmentParser(FakeVl()).parse(Path('not-read.jpg'),'doc-example','doc-example-book')
page=parsed.page_ir
items=parsed.accessible_page['focus_items']
duplicate=deepcopy(page)
duplicate['reading_order']=duplicate['reading_order']+[items[0]['id']] if 'id' in items[0] else duplicate['reading_order']+[items[0]['focus_item_id']]
dup_items=flatten_page(duplicate)['focus_items']
damaged=deepcopy(blocks)
damaged[0]['block_bbox']=None
missing=PaddleVlFragmentParser(FakeVl(damaged)).parse(Path('not-read.jpg'),'doc-missing','doc-example-book')

def pair(n,l,r):
    return OpaqueFooterTokenPair(l,r,FrameId(f'doc-{n}'),n/10,'preview_native','fake:raw',f'{n:064x}',f'{n+100:064x}')
reference=OpaqueReferenceBank(ArtifactId('doc-reference'),'doc-receipt','doc-pack',tuple(pair(n,'26','27') for n in range(1,6)),'fake')
identity={}
for name,values in {'same':[('26','27')],
                    'changed':[('28','29')]*5,
                    'inconsistent':[('28','29'),('2B','29'),('28','2g'),('23','29'),('28','9')]}.items():
    collector=OpaqueQueryCollector(OpaqueFooterIdentityPolicy(),[reference],started_at=0)
    steps=[]
    for n,(l,r) in enumerate(values,start=6):
        decision=collector.observe(pair(n,l,r))
        steps.append({'pair':[l,r],'decision':decision.kind.value,
                      'valid':decision.valid_observations,
                      'consensus':decision.novel_consensus_count,
                      'numeric_corroboration':decision.coherent_numeric_difference})
    identity[name]=steps

equation_cells=math_focus_item_to_braille({'ast_status':math[0]['status'],'presentation_ast':math[0]['ast']})
equation_windows=[build_frame('equation-example',equation_cells,0,10),scroll('equation-example',equation_cells,0,10,'RIGHT')]
result={'equation_windows':equation_windows,'scope':'controlled text/VL-result/raw-pair fixtures; no OCR inference or physical output',
        'math':math,'page':{'input_blocks':blocks,'page_ir':page,'accessible_page':parsed.accessible_page,
                           'validation':parsed.validation,
                           'focus_count':len(items),'duplicate_member_reference_focus_count':len(dup_items)},
        'bad_formula_bbox':{'schema_valid':missing.validation['schema_valid'],
                            'focus_count':len(missing.accessible_page['focus_items']),
                            'focus_kinds':[i['kind'] for i in missing.accessible_page['focus_items']]},
        'identity':identity}
print(json.dumps(result,ensure_ascii=False,indent=2))
