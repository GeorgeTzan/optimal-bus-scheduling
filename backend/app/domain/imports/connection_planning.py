"""Preview an entire connection graph after the proposed workbook transaction."""
from app.domain.imports.catalog import ref_existing,ref_row,ref_key
from app.domain.timetables.connection_graph import linear_chains,ConnectionGraphError


def plan_connections(planner):
    rows=[row for row in planner.rows if row.entity=='connections']
    if not rows:return
    current=planner.catalog.connection_rows()
    existing={(row.incoming_template_id,row.outgoing_template_id):row for row in current}
    edges={(ref_key(ref_existing('timetable',row.incoming_template_id)),ref_key(ref_existing('timetable',row.outgoing_template_id))):row.is_active for row in current}
    seen={}
    for row in rows:
        if row.plan['issues']:continue
        incoming=planner.record_ref(row,'timetable',row.values['incoming_ref'],'incoming_ref')
        outgoing=planner.record_ref(row,'timetable',row.values['outgoing_ref'],'outgoing_ref')
        if row.plan['issues'] or not incoming or not outgoing:continue
        pair=(ref_key(incoming),ref_key(outgoing))
        if pair in seen:
            for duplicate in (seen[pair],row):
                planner.error(duplicate,'duplicate_connection','Review each connection once in this file.','Δηλώστε κάθε σύνδεση μία φορά στο αρχείο.','outgoing_ref')
            continue
        seen[pair]=row
        if pair[0]==pair[1]:
            planner.error(row,'connection_cycle','Choose two different services.','Επιλέξτε δύο διαφορετικά δρομολόγια.','outgoing_ref');continue
        target=existing.get((incoming.get('id'),outgoing.get('id')))
        active=row.values.get('is_active',target.is_active if target else True)
        if active:
            for field,ref in (('incoming_ref',incoming),('outgoing_ref',outgoing)):
                if not planner.active(ref):planner.error(row,'inactive_reference','Choose an active service or correct its row first.','Επιλέξτε ενεργό δρομολόγιο ή διορθώστε πρώτα τη γραμμή του.','incoming_ref' if field=='incoming_ref' else 'outgoing_ref')
        row.planned_reference = row.values['incoming_ref'] + ' → ' + row.values['outgoing_ref']
        row.plan.update(target={'id':target.id,'version':target.version} if target else None,
            ref=ref_existing('connections',target.id) if target else ref_row('connections',row.id),
            payload={'is_active':active},relations={'incoming_template_id':incoming,'outgoing_template_id':outgoing},
            before={'is_active':target.is_active} if target else {},changed_fields=['is_active'] if target and target.is_active!=active else [],
            action='new' if target is None else 'update' if target.is_active!=active else 'unchanged',aliases=[])
        edges[pair]=active
    try:linear_chains(pair for pair,active in edges.items() if active)
    except ConnectionGraphError as error:
        for row in rows:
            planner.error(row,error.code,str(error),'Κάθε δρομολόγιο μπορεί να έχει μία προηγούμενη και μία επόμενη σύνδεση, χωρίς κύκλους.','outgoing_ref')
