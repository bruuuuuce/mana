package fixture;
import org.springframework.stereotype.Service;
import org.springframework.beans.factory.annotation.Autowired;
@Service class Entry {
    @Autowired Sink sink;
    public void run() { sink.required(); }
}
class Container { static class Replacement extends Sink {} }
