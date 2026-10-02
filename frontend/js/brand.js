/* Runtime product identity comes from /api/v1/meta (project.json on the server). */
export const fallbackBrand=Object.freeze({
  productName:'AuraLAN',shortName:'AuraLAN',tagline:'Your network, clearly.',
  version:'1.0.0',apiVersion:'v1',accent:{primary:'#3B82F6',soft:'#EAF2FF'},repository:{}
});
export function normalizeBrand(meta){return{...fallbackBrand,...(meta?.brand||meta||{})};}
