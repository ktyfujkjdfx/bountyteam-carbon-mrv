import Ajv2020 from 'ajv/dist/2020';
import addFormats from 'ajv-formats';
import apiModels from '../../contracts/api-models.schema.json';

const ajv = new Ajv2020({ strict: false, allErrors: true });
addFormats(ajv);
ajv.addSchema(apiModels);

const schemaId = (apiModels as { $id: string }).$id;

export type SchemaName = keyof (typeof apiModels)['components']['schemas'];

export function schemaErrors(name: SchemaName, value: unknown): string[] {
  const validate = ajv.getSchema(`${schemaId}#/components/schemas/${name}`);
  if (!validate) throw new Error(`schema ${name} not found`);
  if (validate(value)) return [];
  return (validate.errors ?? []).map((e) => `${e.instancePath} ${e.message ?? ''}`);
}

export function expectSchema(name: SchemaName, value: unknown): void {
  const errors = schemaErrors(name, value);
  if (errors.length > 0) {
    throw new Error(`${name} does not match contracts/api-models.schema.json:\n${errors.join('\n')}\n${JSON.stringify(value, null, 2).slice(0, 2000)}`);
  }
}

export function enumOf(name: SchemaName, property: string): string[] {
  const schemas = (apiModels as unknown as { components: { schemas: Record<string, { properties: Record<string, { enum?: string[] }> }> } })
    .components.schemas;
  const values = schemas[name]?.properties[property]?.enum;
  if (!values) throw new Error(`${name}.${property} has no enum`);
  return values;
}
