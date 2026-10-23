package fixture;

import external.model.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class Wildcard {
    @Transactional public void unique(Payload value) {}
    @Transactional public void ambiguous(Payload value) {}
    @Transactional public void ambiguous(int value) {}
}
